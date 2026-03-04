from __future__ import annotations

"""Todo 子系统对外依赖的 Ports/Protocols。

设计目标：
- Todo 目录内的编排/控制器/桥接层只依赖这些稳定协议，不直接依赖主窗口、GraphView 或 EditorExecutor 的具体实现；
- 具体实现通过 Adapter 形式注入（例如主窗口适配、共享画布租约管理器、执行器提供者等）。

注意：
- 这里只描述 Todo 实际需要的最小能力集；
- 不使用 try/except；前置条件缺失应通过显式错误暴露。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from app.ui.execution.execution_session import ExecutionSession


class _SignalLike(Protocol):
    def connect(self, slot: object) -> None: ...


@runtime_checkable
class GraphViewPort(Protocol):
    """Todo 侧需要的最小 GraphView 能力集合（只读预览 / 联动用）。"""

    # --- basic toggles
    enable_click_signals: bool
    show_coordinates: bool
    node_library: object

    # --- signals
    graph_element_clicked: _SignalLike

    # --- top right
    def set_extra_top_right_button(self, button: object | None) -> None: ...

    # --- scene access (node_library 同步用)
    def scene(self) -> object | None: ...

    # --- highlight / focus surface (PreviewController uses duck typing; keep minimal here)
    def restore_all_opacity(self) -> None: ...


@dataclass(frozen=True)
class GraphPreviewContext:
    """Todo 侧对“图预览上下文”的稳定描述。"""

    graph_id: str
    graph_data: dict
    container: object


@runtime_checkable
class ExecutionMonitorPort(Protocol):
    """执行监控面板对 Todo 暴露的最小端口（稳定合同）。"""

    # --- signals
    execute_clicked: _SignalLike
    execute_remaining_clicked: _SignalLike
    step_anchor_clicked: _SignalLike
    recognition_focus_succeeded: _SignalLike

    # --- runtime state flags
    is_running: bool
    is_paused: bool

    # --- external execute controls (compact mode)
    def set_execute_visible(self, visible: bool) -> None: ...

    def set_execute_text(self, text: str) -> None: ...

    def set_execute_remaining_visible(self, visible: bool) -> None: ...

    def set_execute_remaining_text(self, text: str) -> None: ...

    # --- logging & status
    def start_monitoring(self) -> None: ...

    def log(self, message: str) -> None: ...

    def update_status(self, status: str) -> None: ...

    # --- structured run events
    def begin_run(self, total_steps: int) -> str: ...

    def end_run(self, success: bool, reason: str | None = None) -> None: ...

    def notify_step_started(
        self,
        todo_id: str,
        title: str,
        index: int | None,
        total_steps: int | None,
    ) -> None: ...

    def notify_step_completed(
        self,
        todo_id: str,
        title: str,
        index: int | None,
        total_steps: int | None,
        success: bool,
        reason: str | None = None,
    ) -> None: ...

    def notify_step_skipped(
        self,
        todo_id: str,
        title: str,
        index: int | None,
        total_steps: int | None,
        reason: str,
    ) -> None: ...

    def set_current_step_context(self, step_title: str, parent_title: str) -> None: ...

    def set_current_step_tokens(self, step_id: str, tokens: list) -> None: ...

    # --- pause control
    def request_pause(self) -> None: ...

    def is_step_mode_enabled(self) -> bool: ...

    # --- shared executor
    def get_shared_executor(self) -> object | None: ...

    def set_shared_executor(self, executor: object) -> None: ...

    # --- context injection / session attach
    def set_context(
        self, workspace_path: Path, graph_model: object, graph_view: object | None = None
    ) -> None: ...

    def attach_session(self, session: ExecutionSession) -> None: ...


@runtime_checkable
class ExecutorProviderPort(Protocol):
    """向 Todo 提供（可复用的）执行器实例的端口。"""

    def get_or_create_executor(
        self,
        *,
        workspace_path: Path,
        monitor_port: Optional[ExecutionMonitorPort],
    ) -> object: ...


@runtime_checkable
class TodoHostPort(Protocol):
    """Todo 子系统宿主对外能力（主窗口/运行时服务/导航）最小集合。"""

    def try_get_workspace_path(self) -> Optional[Path]: ...

    def try_get_node_library(self) -> Optional[object]: ...

    def try_get_current_package(self) -> Optional[object]: ...

    def get_graph_data_service(self) -> object: ...

    def ensure_execution_monitor(self, *, switch_to: bool = False) -> Optional[ExecutionMonitorPort]: ...

    def try_get_execution_monitor(self) -> Optional[ExecutionMonitorPort]: ...

    def open_graph_in_editor(self, graph_id: str, graph_data: dict, container: object) -> None: ...


