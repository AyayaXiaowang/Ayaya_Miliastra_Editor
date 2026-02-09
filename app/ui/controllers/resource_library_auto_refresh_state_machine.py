from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine.utils.path_utils import normalize_slash


@dataclass(frozen=True)
class ResourceLibraryAutoRefreshConfig:
    debounce_ms: int
    max_delay_ms: int
    internal_write_ignore_seconds: float


class InternalWriteSuppression:
    """用于抑制“内部写盘导致的目录变化事件”，避免误触发自动刷新。"""

    def __init__(self, ignore_seconds: float) -> None:
        self._ignore_seconds = float(ignore_seconds)
        self._last_internal_write_wall_time_seconds: float = 0.0
        # None：忽略所有目录事件（保留旧行为，适用于“整包保存”等写盘风暴）。
        # ""：未记录目录（仅用于初始态或复位态）。
        # 其他：记录最后一次内部写盘对应目录的规范化文本（用于按目录粒度抑制）。
        self._last_internal_write_directory_text: str | None = ""

    @property
    def last_internal_write_wall_time_seconds(self) -> float:
        return float(self._last_internal_write_wall_time_seconds)

    @staticmethod
    def _normalize_directory_text(directory_path: Path) -> str:
        return normalize_slash(str(directory_path)).rstrip("/").lower()

    def record_internal_write(self, *, wall_time_seconds: float, directory_path: Path | None) -> None:
        self._last_internal_write_wall_time_seconds = float(wall_time_seconds)
        if directory_path is None:
            self._last_internal_write_directory_text = None
            return
        self._last_internal_write_directory_text = self._normalize_directory_text(directory_path)

    def should_ignore_event(self, *, wall_time_seconds: float, directory_path: Path) -> bool:
        if self._last_internal_write_wall_time_seconds <= 0.0:
            return False

        elapsed_seconds = float(wall_time_seconds) - float(self._last_internal_write_wall_time_seconds)
        if elapsed_seconds >= float(self._ignore_seconds):
            return False

        directory_scope = self._last_internal_write_directory_text
        if directory_scope is None:
            return True

        if not directory_scope:
            return False

        changed_dir_text = self._normalize_directory_text(directory_path)
        if changed_dir_text == directory_scope:
            return True
        return changed_dir_text.startswith(directory_scope + "/")


class RefreshMutualExclusion:
    """刷新互斥：刷新进行中不触发新的刷新，只记录 pending，刷新结束后再复核一次。"""

    def __init__(self) -> None:
        self._in_progress: bool = False
        self._has_pending: bool = False

    @property
    def in_progress(self) -> bool:
        return bool(self._in_progress)

    def mark_started(self) -> None:
        self._in_progress = True

    def mark_completed(self) -> bool:
        self._in_progress = False
        had_pending = bool(self._has_pending)
        self._has_pending = False
        return had_pending

    def mark_pending(self) -> None:
        self._has_pending = True

    def clear_pending(self) -> None:
        self._has_pending = False


class FingerprintRecheckCoordinator:
    """指纹复核的并发协调：计算进行中时只记一次重算请求，计算结束后再补一次。"""

    def __init__(self) -> None:
        self._compute_in_progress: bool = False
        self._recompute_requested: bool = False

    @property
    def compute_in_progress(self) -> bool:
        return bool(self._compute_in_progress)

    def mark_compute_started(self) -> None:
        self._compute_in_progress = True

    def mark_compute_finished(self) -> None:
        self._compute_in_progress = False

    def request_recompute(self) -> None:
        self._recompute_requested = True

    def consume_recompute_requested(self) -> bool:
        requested = bool(self._recompute_requested)
        self._recompute_requested = False
        return requested


class FingerprintVerification:
    """指纹复核：以指纹差异作为“确实有外部落盘变更”的确认条件。"""

    @staticmethod
    def needs_refresh(*, latest_fingerprint: str, baseline_fingerprint: str) -> bool:
        latest_text = str(latest_fingerprint or "")
        baseline_text = str(baseline_fingerprint or "")
        return bool(latest_text and latest_text != baseline_text)


@dataclass(frozen=True)
class DirectoryChangedEvent:
    directory_path: Path
    wall_time_seconds: float
    monotonic_time_seconds: float


@dataclass(frozen=True)
class DebounceTimerFiredEvent:
    monotonic_time_seconds: float


@dataclass(frozen=True)
class PeriodicRecheckEvent:
    """周期性指纹复核（兜底）。

    设计动机：
    - QFileSystemWatcher 在极端情况下可能因系统限制/目录过多而无法覆盖所有子目录；
    - 部分编辑器/外部工具的写盘方式可能导致 watcher 丢事件；
    - 该事件用于在“无目录事件”时也能按固定周期触发一次指纹复核，
      由状态机统一受刷新互斥/计算互斥策略约束，避免引入刷新风暴。
    """

    monotonic_time_seconds: float


@dataclass(frozen=True)
class FingerprintComputeStartedEvent:
    pass


@dataclass(frozen=True)
class FingerprintComputeStartRejectedEvent:
    pass


@dataclass(frozen=True)
class FingerprintComputedEvent:
    latest_fingerprint: str
    baseline_fingerprint: str


@dataclass(frozen=True)
class RefreshStartedEvent:
    pass


@dataclass(frozen=True)
class RefreshCompletedEvent:
    pass


@dataclass(frozen=True)
class SetEnabledEvent:
    enabled: bool


@dataclass(frozen=True)
class RecordInternalWriteEvent:
    wall_time_seconds: float
    directory_path: Path | None = None


@dataclass(frozen=True)
class ScheduleDebounceTimerAction:
    delay_ms: int


@dataclass(frozen=True)
class RequestFingerprintComputeAction:
    pass


@dataclass(frozen=True)
class RequestRefreshAction:
    pass


AutoRefreshEvent = (
    DirectoryChangedEvent
    | DebounceTimerFiredEvent
    | PeriodicRecheckEvent
    | FingerprintComputeStartedEvent
    | FingerprintComputeStartRejectedEvent
    | FingerprintComputedEvent
    | RefreshStartedEvent
    | RefreshCompletedEvent
    | SetEnabledEvent
    | RecordInternalWriteEvent
)

AutoRefreshAction = ScheduleDebounceTimerAction | RequestFingerprintComputeAction | RequestRefreshAction


class ResourceLibraryAutoRefreshStateMachine:
    """资源库自动刷新状态机（事件→状态→动作）。

    设计边界：
    - 纯逻辑：不依赖 Qt，不启动线程，不直接调用刷新回调；
    - 只决定“何时应该做什么动作”，实际的计时器/线程/刷新由外层桥接；
    - 关键折中点（可靠性优先）：
      - 指纹基线由刷新链路推进：watcher 事件只触发“复核”，不直接推进基线；
      - 去抖 + 最大等待时间合并事件风暴；
      - 刷新互斥：刷新进行中只记录 pending，刷新结束后再复核一次指纹；
      - 内部写盘抑制：短窗口内忽略 watcher 事件。
    """

    def __init__(self, config: ResourceLibraryAutoRefreshConfig) -> None:
        self._config = config
        self._enabled: bool = True

        self._internal_write_suppression = InternalWriteSuppression(config.internal_write_ignore_seconds)
        self._refresh_mutex = RefreshMutualExclusion()
        self._fingerprint_recheck = FingerprintRecheckCoordinator()
        self._fingerprint_verification = FingerprintVerification()

        self._first_change_seen_monotonic_seconds: float = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self._enabled)

    def handle_event(self, event: AutoRefreshEvent) -> list[AutoRefreshAction]:
        if isinstance(event, SetEnabledEvent):
            self._enabled = bool(event.enabled)
            if not self._enabled:
                self._first_change_seen_monotonic_seconds = 0.0
                self._refresh_mutex.clear_pending()
            return []

        if isinstance(event, RecordInternalWriteEvent):
            self._internal_write_suppression.record_internal_write(
                wall_time_seconds=event.wall_time_seconds,
                directory_path=event.directory_path,
            )
            return []

        if not self._enabled:
            return []

        if isinstance(event, DirectoryChangedEvent):
            if self._internal_write_suppression.should_ignore_event(
                wall_time_seconds=event.wall_time_seconds,
                directory_path=event.directory_path,
            ):
                return []

            if self._first_change_seen_monotonic_seconds <= 0.0:
                self._first_change_seen_monotonic_seconds = float(event.monotonic_time_seconds)

            elapsed_ms = int((float(event.monotonic_time_seconds) - float(self._first_change_seen_monotonic_seconds)) * 1000.0)
            remaining_ms = int(self._config.max_delay_ms) - int(elapsed_ms)
            if remaining_ms <= 0:
                scheduled_delay_ms = 0
            else:
                scheduled_delay_ms = min(int(self._config.debounce_ms), int(remaining_ms))

            return [ScheduleDebounceTimerAction(delay_ms=int(max(0, scheduled_delay_ms)))]

        if isinstance(event, DebounceTimerFiredEvent):
            # 本次批次已“到点”：复位 first_seen，开始进入“复核指纹/刷新互斥”链路
            self._first_change_seen_monotonic_seconds = 0.0

            if self._refresh_mutex.in_progress:
                self._refresh_mutex.mark_pending()
                return []

            if self._fingerprint_recheck.compute_in_progress:
                self._fingerprint_recheck.request_recompute()
                return []

            return [RequestFingerprintComputeAction()]

        if isinstance(event, PeriodicRecheckEvent):
            if self._refresh_mutex.in_progress:
                self._refresh_mutex.mark_pending()
                return []

            if self._fingerprint_recheck.compute_in_progress:
                self._fingerprint_recheck.request_recompute()
                return []

            return [RequestFingerprintComputeAction()]

        if isinstance(event, FingerprintComputeStartedEvent):
            self._fingerprint_recheck.mark_compute_started()
            return []

        if isinstance(event, FingerprintComputeStartRejectedEvent):
            self._fingerprint_recheck.request_recompute()
            return []

        if isinstance(event, FingerprintComputedEvent):
            self._fingerprint_recheck.mark_compute_finished()

            needs_refresh = self._fingerprint_verification.needs_refresh(
                latest_fingerprint=str(event.latest_fingerprint or ""),
                baseline_fingerprint=str(event.baseline_fingerprint or ""),
            )

            actions: list[AutoRefreshAction] = []
            if needs_refresh:
                if self._refresh_mutex.in_progress:
                    self._refresh_mutex.mark_pending()
                else:
                    actions.append(RequestRefreshAction())

            if self._fingerprint_recheck.consume_recompute_requested():
                if self._refresh_mutex.in_progress:
                    self._refresh_mutex.mark_pending()
                else:
                    actions.append(RequestFingerprintComputeAction())

            return actions

        if isinstance(event, RefreshStartedEvent):
            self._refresh_mutex.mark_started()
            return []

        if isinstance(event, RefreshCompletedEvent):
            had_pending = self._refresh_mutex.mark_completed()
            if not had_pending:
                return []

            if self._fingerprint_recheck.compute_in_progress:
                self._fingerprint_recheck.request_recompute()
                return []

            return [RequestFingerprintComputeAction()]

        return []


