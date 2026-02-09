from __future__ import annotations

from pathlib import Path

from app.ui.execution import ExecutionSession
from app.ui.todo.todo_ports import ExecutionMonitorPort


class _DummySignal:
    def __init__(self) -> None:
        self._connected: list[object] = []

    def connect(self, slot: object) -> None:
        self._connected.append(slot)


class _DummyExecutionMonitor:
    def __init__(self) -> None:
        self.execute_clicked = _DummySignal()
        self.execute_remaining_clicked = _DummySignal()
        self.step_anchor_clicked = _DummySignal()
        self.recognition_focus_succeeded = _DummySignal()

        self.is_running: bool = False
        self.is_paused: bool = False
        self._shared_executor: object | None = None

    def set_execute_visible(self, visible: bool) -> None:
        _ = visible

    def set_execute_text(self, text: str) -> None:
        _ = text

    def set_execute_remaining_visible(self, visible: bool) -> None:
        _ = visible

    def set_execute_remaining_text(self, text: str) -> None:
        _ = text

    def start_monitoring(self) -> None:
        return

    def log(self, message: str) -> None:
        _ = message

    def update_status(self, status: str) -> None:
        _ = status

    def begin_run(self, total_steps: int) -> str:
        _ = total_steps
        return "run-1"

    def end_run(self, success: bool, reason: str | None = None) -> None:
        _ = success, reason

    def notify_step_started(
        self,
        todo_id: str,
        title: str,
        index: int | None,
        total_steps: int | None,
    ) -> None:
        _ = todo_id, title, index, total_steps

    def notify_step_completed(
        self,
        todo_id: str,
        title: str,
        index: int | None,
        total_steps: int | None,
        success: bool,
        reason: str | None = None,
    ) -> None:
        _ = todo_id, title, index, total_steps, success, reason

    def notify_step_skipped(
        self,
        todo_id: str,
        title: str,
        index: int | None,
        total_steps: int | None,
        reason: str,
    ) -> None:
        _ = todo_id, title, index, total_steps, reason

    def set_current_step_context(self, step_title: str, parent_title: str) -> None:
        _ = step_title, parent_title

    def set_current_step_tokens(self, step_id: str, tokens: list) -> None:
        _ = step_id, tokens

    def request_pause(self) -> None:
        return

    def is_step_mode_enabled(self) -> bool:
        return False

    def get_shared_executor(self) -> object | None:
        return self._shared_executor

    def set_shared_executor(self, executor: object) -> None:
        self._shared_executor = executor

    def set_context(self, workspace_path: Path, graph_model: object, graph_view: object | None = None) -> None:
        _ = workspace_path, graph_model, graph_view

    def attach_session(self, session: ExecutionSession) -> None:
        _ = session


class _MissingMethodMonitor(_DummyExecutionMonitor):
    # runtime_checkable 会校验方法成员是否 callable；将其置为 None 用于模拟缺失
    attach_session = None  # type: ignore[assignment]


def test_execution_monitor_port_runtime_contracts() -> None:
    assert isinstance(_DummyExecutionMonitor(), ExecutionMonitorPort)
    # 缺少关键方法时，应无法通过 runtime_checkable 的协议校验
    assert not isinstance(_MissingMethodMonitor(), ExecutionMonitorPort)


