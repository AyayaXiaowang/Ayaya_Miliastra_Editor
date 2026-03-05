from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from PyQt6 import QtCore

from app.ui.controllers.resource_library_auto_refresh_state_machine import (
    ResourceLibraryAutoRefreshConfig,
    ResourceLibraryAutoRefreshStateMachine,
    DirectoryChangedEvent,
    DebounceTimerFiredEvent,
    FingerprintComputeStartedEvent,
    FingerprintComputeStartRejectedEvent,
    FingerprintComputedEvent,
    RefreshStartedEvent,
    RefreshCompletedEvent,
    RecordInternalWriteEvent,
    SetEnabledEvent,
    ScheduleDebounceTimerAction,
    RequestFingerprintComputeAction,
    RequestRefreshAction,
    PeriodicRecheckEvent,
)
from engine.configs.settings import settings
from engine.resources.resource_manager import ResourceManager
from engine.utils.logging.logger import log_info, log_warn

from .resource_fingerprint_thread import ResourceFingerprintThread


class ResourceAutoRefreshBridge(QtCore.QObject):
    """Qt 桥接：将资源库自动刷新状态机动作落到计时器/线程/回调。"""

    def __init__(
        self,
        resource_manager: ResourceManager,
        *,
        emit_toast: Callable[[str, str], None],
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._resource_manager = resource_manager
        self._emit_toast = emit_toast

        self._refresh_callback: Optional[Callable[[], None]] = None

        debounce_ms = int(getattr(settings, "RESOURCE_LIBRARY_AUTO_REFRESH_DEBOUNCE_MS", 300))
        max_delay_ms = int(getattr(settings, "RESOURCE_LIBRARY_AUTO_REFRESH_MAX_DELAY_MS", 2000))
        internal_ignore_seconds = float(getattr(settings, "RESOURCE_LIBRARY_INTERNAL_WRITE_IGNORE_SECONDS", 0.8))

        self._state_machine = ResourceLibraryAutoRefreshStateMachine(
            ResourceLibraryAutoRefreshConfig(
                debounce_ms=int(debounce_ms),
                max_delay_ms=int(max_delay_ms),
                internal_write_ignore_seconds=float(internal_ignore_seconds),
            )
        )

        self._enabled: bool = bool(getattr(settings, "RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED", True))
        self._state_machine.handle_event(SetEnabledEvent(enabled=bool(self._enabled)))

        self._debounce_timer: Optional[QtCore.QTimer] = None

        # 指纹计算线程：使用 QThread 子类以提升退出稳定性
        self._fingerprint_thread: Optional[ResourceFingerprintThread] = None
        self._active_fingerprint_threads: list[ResourceFingerprintThread] = []

        self._refresh_scheduled: bool = False

        self._periodic_timer: Optional[QtCore.QTimer] = None
        self._periodic_interval_seconds: float = 0.0
        self._is_shutting_down: bool = False

        # ===== 诊断信息（用于排查“后台放置后卡死/长时间无响应”）=====
        self._diag_seq: int = 0
        self._last_trigger_source: str = "init"
        self._last_trigger_directory: Path | None = None
        self._last_trigger_monotonic: float = 0.0

        self._fingerprint_started_monotonic: float = 0.0
        self._fingerprint_trigger_source: str = ""
        self._fingerprint_trigger_directory: Path | None = None
        self._fingerprint_baseline_snapshot: str = ""
        self._last_fingerprint_elapsed_seconds: float = 0.0

        self._refresh_seq: int = 0
        self._refresh_trigger_source: str = ""
        self._refresh_trigger_directory: Path | None = None
        self._refresh_started_monotonic: float = 0.0

        self._last_periodic_tick_log_monotonic: float = 0.0
        self._last_fingerprint_start_log_monotonic: float = 0.0

        # 去抖调度日志限流：避免目录事件风暴把 UI/控制台刷死
        self._debounce_schedule_total_count: int = 0
        self._debounce_schedule_since_last_log: int = 0
        self._debounce_schedule_last_log_monotonic: float = 0.0
        self._debounce_schedule_last_dir: Path | None = None
        self._debounce_schedule_last_delay_ms: int = 0

    def set_refresh_callback(self, callback: Optional[Callable[[], None]]) -> None:
        self._refresh_callback = callback

    def notify_refresh_started(self) -> None:
        """由上层在“实际刷新任务开始”时调用（刷新后台化后不再由本类包裹回调）。"""
        self._refresh_started_monotonic = float(time.monotonic())
        log_warn(
            "[AUTO-REFRESH] 刷新任务开始：refresh_seq={}, source={}, dir={}",
            int(self._refresh_seq),
            str(self._refresh_trigger_source),
            str(self._refresh_trigger_directory) if self._refresh_trigger_directory is not None else "",
        )
        self._state_machine.handle_event(RefreshStartedEvent())

    def notify_refresh_completed(self) -> None:
        """由上层在“实际刷新任务完成（含主线程提交替换）”时调用。"""
        self._state_machine.handle_event(RefreshCompletedEvent())
        elapsed = float(time.monotonic()) - float(self._refresh_started_monotonic or time.monotonic())
        log_warn(
            "[AUTO-REFRESH] 刷新任务完成：refresh_seq={}, elapsed={:.2f}s",
            int(self._refresh_seq),
            float(elapsed),
        )

    def set_enabled(self, enabled: bool) -> None:
        normalized = bool(enabled)
        self._enabled = normalized
        self._state_machine.handle_event(SetEnabledEvent(enabled=bool(normalized)))
        log_info("[AUTO-REFRESH] set_enabled={}", bool(normalized))
        if not normalized:
            if self._debounce_timer is not None:
                self._debounce_timer.stop()
            self._stop_periodic_timer()
            return
        if self._periodic_interval_seconds > 0.0:
            self._ensure_periodic_timer()

    def record_internal_write(self, directory_path: Path | None = None) -> None:
        self._state_machine.handle_event(
            RecordInternalWriteEvent(
                wall_time_seconds=float(time.time()),
                directory_path=directory_path,
            )
        )

    def notify_directory_changed_path(self, directory_path: Path) -> None:
        """显式入口：目录变化已被解析为 Path。"""
        if self._is_shutting_down:
            return
        if not self._enabled:
            return
        if QtCore.QCoreApplication.instance() is None or QtCore.QCoreApplication.closingDown():
            return
        self._diag_seq += 1
        self._last_trigger_source = "directoryChanged"
        self._last_trigger_directory = directory_path
        self._last_trigger_monotonic = float(time.monotonic())
        self._handle_event(
            DirectoryChangedEvent(
                directory_path=directory_path,
                wall_time_seconds=float(time.time()),
                monotonic_time_seconds=float(time.monotonic()),
            )
        )

    def set_periodic_recheck_interval_seconds(self, seconds: float) -> None:
        interval = float(seconds)
        if interval <= 0.0:
            self._periodic_interval_seconds = 0.0
            self._stop_periodic_timer()
            return
        self._periodic_interval_seconds = interval
        self._ensure_periodic_timer()

    def enable_periodic_recheck_fallback_if_needed(self, *, add_failure_count: int) -> None:
        """当 watcher 无法覆盖全部目录时，启用周期性复核作为兜底。"""
        if not self._enabled:
            return
        if int(add_failure_count) <= 0:
            return

        # 用户显式配置优先；否则使用保守的默认值（降低漏刷新概率）。
        configured = float(getattr(settings, "RESOURCE_LIBRARY_AUTO_REFRESH_PERIODIC_RECHECK_SECONDS", 0.0))
        fallback_seconds = configured if configured > 0.0 else 5.0
        if self._periodic_interval_seconds > 0.0:
            return
        self.set_periodic_recheck_interval_seconds(float(fallback_seconds))
        log_warn(
            "[AUTO-REFRESH] watcher 覆盖不足，启用周期性指纹复核兜底：interval_seconds={}, add_failures={}",
            float(fallback_seconds),
            int(add_failure_count),
        )
        self._emit_toast(
            "资源库目录监听未完全建立，已启用周期性指纹复核以降低漏刷新概率",
            "warning",
        )

    # ===== 内部：状态机动作处理 =====

    def _ensure_debounce_timer(self) -> QtCore.QTimer:
        if self._debounce_timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._on_debounce_timer_fired)
            self._debounce_timer = timer
        return self._debounce_timer

    def _on_debounce_timer_fired(self) -> None:
        self._handle_event(DebounceTimerFiredEvent(monotonic_time_seconds=float(time.monotonic())))

    def _handle_event(self, event) -> None:
        if self._is_shutting_down:
            return
        actions = self._state_machine.handle_event(event)
        self._handle_actions(actions)

    def _handle_actions(self, actions) -> None:
        if self._is_shutting_down:
            return
        for action in actions:
            if isinstance(action, ScheduleDebounceTimerAction):
                timer = self._ensure_debounce_timer()
                delay_ms = int(max(0, int(action.delay_ms)))

                # 关键：目录事件风暴下，若持续 stop+start(0)，timeout 永远没有机会被执行，
                # 进而导致状态机无法推进到“指纹复核”阶段，只剩无限刷屏与卡死。
                # 因此：
                # - 如果已有更早的 timer（remainingTime 更小），不延后；
                # - 当 delay_ms 变为 0 且当前 remainingTime > 0 时，允许提前到 0；
                # - 当 remainingTime 已为 0 时，不重复 stop/start，给事件循环一次喘息机会。
                should_restart = False
                if timer.isActive():
                    remaining = int(timer.remainingTime())
                    if delay_ms <= 0:
                        should_restart = remaining > 0
                    else:
                        should_restart = remaining < 0 or remaining > delay_ms
                else:
                    should_restart = True

                if should_restart:
                    timer.stop()
                    timer.start(int(delay_ms))

                self._debounce_schedule_total_count += 1
                self._debounce_schedule_since_last_log += 1
                self._debounce_schedule_last_dir = self._last_trigger_directory
                self._debounce_schedule_last_delay_ms = int(delay_ms)

                now_monotonic = float(time.monotonic())
                if (now_monotonic - float(self._debounce_schedule_last_log_monotonic)) >= 1.0:
                    self._debounce_schedule_last_log_monotonic = now_monotonic
                    since_last = int(self._debounce_schedule_since_last_log)
                    self._debounce_schedule_since_last_log = 0
                    log_info(
                        "[AUTO-REFRESH] 目录变化去抖：pending_events={}, delay_ms={}, remaining_ms={}, dir={}",
                        int(since_last),
                        int(delay_ms),
                        int(timer.remainingTime()) if timer.isActive() else -1,
                        str(self._debounce_schedule_last_dir) if self._debounce_schedule_last_dir is not None else "",
                    )
                continue
            if isinstance(action, RequestFingerprintComputeAction):
                started = self._start_fingerprint_compute()
                if started:
                    self._state_machine.handle_event(FingerprintComputeStartedEvent())
                else:
                    self._state_machine.handle_event(FingerprintComputeStartRejectedEvent())
                continue
            if isinstance(action, RequestRefreshAction):
                self._refresh_trigger_source = str(self._fingerprint_trigger_source or self._last_trigger_source or "")
                self._refresh_trigger_directory = self._fingerprint_trigger_directory or self._last_trigger_directory
                self._refresh_seq += 1
                log_warn(
                    "[AUTO-REFRESH] 指纹差异确认，需要刷新资源库：refresh_seq={}, source={}, dir={}",
                    int(self._refresh_seq),
                    str(self._refresh_trigger_source),
                    str(self._refresh_trigger_directory) if self._refresh_trigger_directory is not None else "",
                )
                self._schedule_refresh_callback()
                continue

    def _start_fingerprint_compute(self) -> bool:
        if self._is_shutting_down:
            return False
        if not self._enabled:
            return False
        if QtCore.QCoreApplication.instance() is None or QtCore.QCoreApplication.closingDown():
            return False
        if self._fingerprint_thread is not None:
            return False

        now_monotonic = float(time.monotonic())
        self._fingerprint_started_monotonic = now_monotonic
        self._fingerprint_trigger_source = str(self._last_trigger_source or "")
        self._fingerprint_trigger_directory = self._last_trigger_directory
        self._fingerprint_baseline_snapshot = str(self._resource_manager.get_resource_library_fingerprint() or "")

        # 周期性复核可能很频繁：仅做低频日志，避免刷屏
        if self._fingerprint_trigger_source != "periodic_recheck":
            log_info(
                "[AUTO-REFRESH] 开始计算资源库指纹：source={}, dir={}",
                str(self._fingerprint_trigger_source),
                str(self._fingerprint_trigger_directory) if self._fingerprint_trigger_directory is not None else "",
            )
        else:
            if (now_monotonic - float(self._last_fingerprint_start_log_monotonic)) >= 60.0:
                self._last_fingerprint_start_log_monotonic = now_monotonic
                log_info(
                    "[AUTO-REFRESH] 周期性复核：开始计算资源库指纹（每分钟最多提示一次）：interval_seconds={}",
                    float(self._periodic_interval_seconds),
                )

        fingerprint_thread = ResourceFingerprintThread(
            self._resource_manager,
            trigger_directory=self._fingerprint_trigger_directory,
            baseline_fingerprint=str(self._fingerprint_baseline_snapshot or ""),
            parent=self,
        )
        self._active_fingerprint_threads.append(fingerprint_thread)
        self._fingerprint_thread = fingerprint_thread
        fingerprint_thread.fingerprint_computed.connect(self._on_fingerprint_computed)
        fingerprint_thread.finished.connect(lambda: self._on_fingerprint_thread_finished(fingerprint_thread))
        fingerprint_thread.finished.connect(fingerprint_thread.deleteLater)
        fingerprint_thread.start()
        return True

    def _on_fingerprint_computed(self, latest_fingerprint: str) -> None:
        # 允许状态机在同一轮事件处理中立即发起下一次复核（短窗口内可能连续请求）
        self._fingerprint_thread = None

        elapsed_seconds = 0.0
        started_at = float(self._fingerprint_started_monotonic)
        if started_at > 0.0:
            elapsed_seconds = float(time.monotonic()) - started_at
        self._last_fingerprint_elapsed_seconds = float(elapsed_seconds)

        baseline_fingerprint = str(self._fingerprint_baseline_snapshot or "")
        latest_text = str(latest_fingerprint or "")
        baseline_text = str(baseline_fingerprint or "")
        fingerprint_changed = bool(latest_text and latest_text != baseline_text)

        # 仅在“指纹确实变化”或“计算明显偏慢”时打印详细日志，避免周期性复核刷屏。
        if fingerprint_changed or elapsed_seconds >= 1.0:
            latest_preview = latest_text if len(latest_text) <= 200 else (latest_text[:197] + "...")
            baseline_preview = baseline_text if len(baseline_text) <= 200 else (baseline_text[:197] + "...")
            log_warn(
                "[AUTO-REFRESH] 指纹复核完成：elapsed={:.2f}s, changed={}, source={}, dir={}, latest_fp={}, baseline_fp={}",
                float(elapsed_seconds),
                bool(fingerprint_changed),
                str(self._fingerprint_trigger_source or ""),
                str(self._fingerprint_trigger_directory) if self._fingerprint_trigger_directory is not None else "",
                str(latest_preview),
                str(baseline_preview),
            )

        self._handle_event(
            FingerprintComputedEvent(
                latest_fingerprint=str(latest_fingerprint or ""),
                baseline_fingerprint=str(baseline_text or ""),
            )
        )

    def _on_fingerprint_thread_finished(self, finished_thread: ResourceFingerprintThread) -> None:
        if self._fingerprint_thread is finished_thread:
            self._fingerprint_thread = None
        if finished_thread in self._active_fingerprint_threads:
            self._active_fingerprint_threads.remove(finished_thread)

    def _schedule_refresh_callback(self) -> None:
        if self._refresh_callback is None:
            return
        if self._refresh_scheduled:
            return
        if self._is_shutting_down:
            return
        if QtCore.QCoreApplication.instance() is None or QtCore.QCoreApplication.closingDown():
            return
        self._refresh_scheduled = True
        # 排队到事件循环，避免在 watcher 回调堆栈里同步执行重活造成重入与卡顿感。
        QtCore.QTimer.singleShot(0, self._perform_refresh_callback)

    def _perform_refresh_callback(self) -> None:
        self._refresh_scheduled = False
        refresh_callback = self._refresh_callback
        if refresh_callback is None:
            return
        if self._is_shutting_down:
            return
        if QtCore.QCoreApplication.instance() is None or QtCore.QCoreApplication.closingDown():
            return

        log_warn(
            "[AUTO-REFRESH] 请求刷新资源库：refresh_seq={}, source={}, dir={}",
            int(self._refresh_seq),
            str(self._refresh_trigger_source),
            str(self._refresh_trigger_directory) if self._refresh_trigger_directory is not None else "",
        )
        refresh_callback()

    # ===== 周期性复核（兜底）=====

    def _ensure_periodic_timer(self) -> None:
        if self._periodic_timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(False)
            timer.timeout.connect(self._on_periodic_timer)
            self._periodic_timer = timer
        interval_ms = int(max(1000, int(self._periodic_interval_seconds * 1000.0)))
        self._periodic_timer.stop()
        self._periodic_timer.start(interval_ms)

    def _stop_periodic_timer(self) -> None:
        if self._periodic_timer is not None:
            self._periodic_timer.stop()

    def _on_periodic_timer(self) -> None:
        if self._is_shutting_down:
            return
        if not self._enabled:
            return
        now_monotonic = float(time.monotonic())
        self._diag_seq += 1
        self._last_trigger_source = "periodic_recheck"
        self._last_trigger_directory = None
        self._last_trigger_monotonic = now_monotonic
        if (now_monotonic - float(self._last_periodic_tick_log_monotonic)) >= 60.0:
            self._last_periodic_tick_log_monotonic = now_monotonic
            log_info(
                "[AUTO-REFRESH] 周期性指纹复核 tick（每分钟最多提示一次）：interval_seconds={}",
                float(self._periodic_interval_seconds),
            )
        self._handle_event(PeriodicRecheckEvent(monotonic_time_seconds=float(time.monotonic())))

    # ===== 清理 =====

    def cleanup(self) -> None:
        self._is_shutting_down = True
        self._enabled = False
        self._state_machine.handle_event(SetEnabledEvent(enabled=False))
        self._refresh_callback = None
        self._refresh_scheduled = False
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
            self._debounce_timer.deleteLater()
            self._debounce_timer = None
        self._stop_periodic_timer()
        if self._periodic_timer is not None:
            self._periodic_timer.deleteLater()
            self._periodic_timer = None

        threads_to_stop = list(self._active_fingerprint_threads)
        self._active_fingerprint_threads.clear()
        for fingerprint_thread in threads_to_stop:
            fingerprint_thread.requestInterruption()
            fingerprint_thread.wait()
        self._fingerprint_thread = None


