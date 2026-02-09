from __future__ import annotations

from pathlib import Path

from app.ui.controllers.resource_library_auto_refresh_state_machine import (
    ResourceLibraryAutoRefreshConfig,
    ResourceLibraryAutoRefreshStateMachine,
    DirectoryChangedEvent,
    DebounceTimerFiredEvent,
    PeriodicRecheckEvent,
    FingerprintComputeStartedEvent,
    FingerprintComputedEvent,
    RefreshCompletedEvent,
    RefreshStartedEvent,
    RecordInternalWriteEvent,
    ScheduleDebounceTimerAction,
    RequestFingerprintComputeAction,
    RequestRefreshAction,
    SetEnabledEvent,
)


def test_directory_events_are_debounced_with_max_delay() -> None:
    state_machine = ResourceLibraryAutoRefreshStateMachine(
        ResourceLibraryAutoRefreshConfig(debounce_ms=300, max_delay_ms=2000, internal_write_ignore_seconds=0.8)
    )

    actions_first = state_machine.handle_event(
        DirectoryChangedEvent(directory_path=Path("资源库"), wall_time_seconds=1000.0, monotonic_time_seconds=200.0)
    )
    assert actions_first == [ScheduleDebounceTimerAction(delay_ms=300)]

    # 1s 之后再次变化：仍应使用 debounce 300ms
    actions_second = state_machine.handle_event(
        DirectoryChangedEvent(directory_path=Path("资源库"), wall_time_seconds=1001.0, monotonic_time_seconds=201.0)
    )
    assert actions_second == [ScheduleDebounceTimerAction(delay_ms=300)]

    # 超过 max_delay：应被压缩为 0ms 立即触发批处理
    actions_third = state_machine.handle_event(
        DirectoryChangedEvent(directory_path=Path("资源库"), wall_time_seconds=1002.2, monotonic_time_seconds=202.2)
    )
    assert actions_third == [ScheduleDebounceTimerAction(delay_ms=0)]


def test_timer_fired_requests_fingerprint_compute_when_idle() -> None:
    state_machine = ResourceLibraryAutoRefreshStateMachine(
        ResourceLibraryAutoRefreshConfig(debounce_ms=300, max_delay_ms=2000, internal_write_ignore_seconds=0.8)
    )

    state_machine.handle_event(
        DirectoryChangedEvent(directory_path=Path("资源库"), wall_time_seconds=1000.0, monotonic_time_seconds=200.0)
    )
    actions = state_machine.handle_event(DebounceTimerFiredEvent(monotonic_time_seconds=200.3))
    assert actions == [RequestFingerprintComputeAction()]


def test_compute_in_progress_causes_recompute_after_finish() -> None:
    state_machine = ResourceLibraryAutoRefreshStateMachine(
        ResourceLibraryAutoRefreshConfig(debounce_ms=300, max_delay_ms=2000, internal_write_ignore_seconds=0.8)
    )

    state_machine.handle_event(FingerprintComputeStartedEvent())
    actions_timer = state_machine.handle_event(DebounceTimerFiredEvent(monotonic_time_seconds=123.0))
    assert actions_timer == []

    actions_after_finish = state_machine.handle_event(
        FingerprintComputedEvent(latest_fingerprint="same", baseline_fingerprint="same")
    )
    assert actions_after_finish == [RequestFingerprintComputeAction()]


def test_fingerprint_difference_requests_refresh_and_refresh_mutual_exclusion() -> None:
    state_machine = ResourceLibraryAutoRefreshStateMachine(
        ResourceLibraryAutoRefreshConfig(debounce_ms=300, max_delay_ms=2000, internal_write_ignore_seconds=0.8)
    )

    actions = state_machine.handle_event(FingerprintComputedEvent(latest_fingerprint="new", baseline_fingerprint="old"))
    assert actions == [RequestRefreshAction()]

    state_machine.handle_event(RefreshStartedEvent())
    actions_during_refresh = state_machine.handle_event(DebounceTimerFiredEvent(monotonic_time_seconds=1.0))
    assert actions_during_refresh == []

    actions_after_refresh = state_machine.handle_event(RefreshCompletedEvent())
    assert actions_after_refresh == [RequestFingerprintComputeAction()]


def test_internal_write_suppression_ignores_nearby_directory_events() -> None:
    state_machine = ResourceLibraryAutoRefreshStateMachine(
        ResourceLibraryAutoRefreshConfig(debounce_ms=300, max_delay_ms=2000, internal_write_ignore_seconds=0.8)
    )

    state_machine.handle_event(RecordInternalWriteEvent(wall_time_seconds=1000.0))
    actions_ignored = state_machine.handle_event(
        DirectoryChangedEvent(directory_path=Path("资源库"), wall_time_seconds=1000.5, monotonic_time_seconds=1.0)
    )
    assert actions_ignored == []

    actions_not_ignored = state_machine.handle_event(
        DirectoryChangedEvent(directory_path=Path("资源库"), wall_time_seconds=1000.9, monotonic_time_seconds=2.0)
    )
    assert actions_not_ignored == [ScheduleDebounceTimerAction(delay_ms=300)]


def test_internal_write_suppression_can_be_scoped_to_specific_directory() -> None:
    state_machine = ResourceLibraryAutoRefreshStateMachine(
        ResourceLibraryAutoRefreshConfig(debounce_ms=300, max_delay_ms=2000, internal_write_ignore_seconds=0.8)
    )

    # 仅记录某个目录的“内部写盘”：应只抑制该目录（及其子目录）内的 directoryChanged 事件
    state_machine.handle_event(
        RecordInternalWriteEvent(
            wall_time_seconds=1000.0,
            directory_path=Path("assets/资源库/项目存档/测试项目/节点图/server/模板示例"),
        )
    )

    actions_ignored = state_machine.handle_event(
        DirectoryChangedEvent(
            directory_path=Path("assets/资源库/项目存档/测试项目/节点图/server/模板示例"),
            wall_time_seconds=1000.5,
            monotonic_time_seconds=1.0,
        )
    )
    assert actions_ignored == []

    actions_other_dir_not_ignored = state_machine.handle_event(
        DirectoryChangedEvent(
            directory_path=Path("assets/资源库/项目存档/测试项目/管理配置"),
            wall_time_seconds=1000.5,
            monotonic_time_seconds=1.1,
        )
    )
    assert actions_other_dir_not_ignored == [ScheduleDebounceTimerAction(delay_ms=300)]


def test_disabled_state_machine_drops_events() -> None:
    state_machine = ResourceLibraryAutoRefreshStateMachine(
        ResourceLibraryAutoRefreshConfig(debounce_ms=300, max_delay_ms=2000, internal_write_ignore_seconds=0.8)
    )

    state_machine.handle_event(SetEnabledEvent(enabled=False))
    actions = state_machine.handle_event(
        DirectoryChangedEvent(directory_path=Path("资源库"), wall_time_seconds=1.0, monotonic_time_seconds=1.0)
    )
    assert actions == []


def test_periodic_recheck_requests_fingerprint_compute_when_idle() -> None:
    state_machine = ResourceLibraryAutoRefreshStateMachine(
        ResourceLibraryAutoRefreshConfig(debounce_ms=300, max_delay_ms=2000, internal_write_ignore_seconds=0.8)
    )

    actions = state_machine.handle_event(PeriodicRecheckEvent(monotonic_time_seconds=123.0))
    assert actions == [RequestFingerprintComputeAction()]


def test_periodic_recheck_is_mutually_exclusive_with_refresh_and_compute() -> None:
    state_machine = ResourceLibraryAutoRefreshStateMachine(
        ResourceLibraryAutoRefreshConfig(debounce_ms=300, max_delay_ms=2000, internal_write_ignore_seconds=0.8)
    )

    state_machine.handle_event(RefreshStartedEvent())
    actions_during_refresh = state_machine.handle_event(PeriodicRecheckEvent(monotonic_time_seconds=1.0))
    assert actions_during_refresh == []

    actions_after_refresh = state_machine.handle_event(RefreshCompletedEvent())
    assert actions_after_refresh == [RequestFingerprintComputeAction()]

    state_machine.handle_event(FingerprintComputeStartedEvent())
    actions_during_compute = state_machine.handle_event(PeriodicRecheckEvent(monotonic_time_seconds=2.0))
    assert actions_during_compute == []

    actions_after_compute = state_machine.handle_event(
        FingerprintComputedEvent(latest_fingerprint="same", baseline_fingerprint="same")
    )
    assert actions_after_compute == [RequestFingerprintComputeAction()]


