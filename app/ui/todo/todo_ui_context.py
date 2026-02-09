from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, TYPE_CHECKING

from app.runtime.services.graph_data_service import GraphDataService, get_shared_graph_data_service
from app.ui.todo.current_todo_resolver import (
    CurrentTodoContext,
    get_selected_todo_id_from_tree,
    resolve_current_todo_for_leaf,
)
from app.ui.todo.todo_ports import ExecutionMonitorPort

if TYPE_CHECKING:
    from app.models import TodoItem
    from app.ui.todo.todo_list_widget import TodoListWidget


class _AppStateProtocol(Protocol):
    workspace_path: str
    node_library: object
    graph_view: object
    resource_manager: object
    package_index_manager: object


class _RightPanelProtocol(Protocol):
    def ensure_visible(self, tab_id: str, *, visible: bool, switch_to: bool) -> None: ...

    def get_widget(self, tab_id: str) -> Optional[object]: ...


class _PackageControllerProtocol(Protocol):
    current_package: object


class _MainWindowProtocol(Protocol):
    app_state: _AppStateProtocol
    right_panel: _RightPanelProtocol
    package_controller: _PackageControllerProtocol

    def register_graph_editor_todo_context(
        self, todo_id: str, detail_info: dict, todo_title: str = ""
    ) -> None: ...

    nav_coordinator: object


@dataclass(frozen=True)
class TodoUiContext:
    """任务清单 UI 的强类型单一入口上下文。

    统一承载：
    - 主窗口依赖解析（app_state / right_panel / package_controller）
    - 执行监控面板获取与显隐
    - graph_data_service 获取
    - 当前 Todo 解析（CurrentTodoContext）
    """

    host: "TodoListWidget"

    # --------------------------------------------------------------------- Main window / app state
    def get_main_window(self) -> Optional[_MainWindowProtocol]:
        return self.host.main_window

    def get_app_state(self) -> Optional[_AppStateProtocol]:
        main_window = self.get_main_window()
        if main_window is None:
            return None
        return main_window.app_state

    def try_get_workspace_path(self) -> Optional[Path]:
        app_state = self.get_app_state()
        if app_state is None:
            return None
        workspace_path_value = app_state.workspace_path or ""
        if not workspace_path_value:
            return None
        return Path(workspace_path_value)

    def try_get_node_library(self) -> Optional[object]:
        app_state = self.get_app_state()
        if app_state is None:
            return None
        return app_state.node_library

    def try_get_current_package(self) -> Optional[object]:
        main_window = self.get_main_window()
        if main_window is None:
            return None
        return main_window.package_controller.current_package

    # --------------------------------------------------------------------- Monitor panel
    def _coerce_execution_monitor_panel(
        self, panel: object | None
    ) -> Optional[ExecutionMonitorPort]:
        if panel is None:
            return None
        if not isinstance(panel, ExecutionMonitorPort):
            raise RuntimeError(
                "右侧面板 'execution_monitor' 未实现 Todo 所需的 ExecutionMonitorPort"
            )
        return panel

    def ensure_execution_monitor(
        self, *, switch_to: bool = False
    ) -> Optional[ExecutionMonitorPort]:
        main_window = self.get_main_window()
        if main_window is None:
            return None
        right_panel = main_window.right_panel
        right_panel.ensure_visible(
            "execution_monitor",
            visible=True,
            switch_to=bool(switch_to),
        )
        panel = self._coerce_execution_monitor_panel(
            right_panel.get_widget("execution_monitor")
        )
        self.host._monitor_window = panel
        return panel

    def try_get_execution_monitor(self) -> Optional[ExecutionMonitorPort]:
        main_window = self.get_main_window()
        if main_window is None:
            return None
        panel = self._coerce_execution_monitor_panel(
            main_window.right_panel.get_widget("execution_monitor")
        )
        if panel is not None:
            self.host._monitor_window = panel
        return panel

    # --------------------------------------------------------------------- Graph data service
    def get_graph_data_service(self) -> GraphDataService:
        app_state = self.get_app_state()
        resource_manager = None
        package_index_manager = None
        if app_state is not None:
            resource_manager = app_state.resource_manager
            package_index_manager = app_state.package_index_manager
        return get_shared_graph_data_service(resource_manager, package_index_manager)

    # --------------------------------------------------------------------- Lazy graph expand dependencies
    def build_graph_expand_dependencies(self) -> Optional[tuple[object, object, object]]:
        """为模板图根懒加载提供 (package, resource_manager, package_index_manager)。

        约定：TreeGraphExpander 不直接依赖 MainWindow 结构，仅消费该三元组。
        """
        current_package = self.try_get_current_package()
        app_state = self.get_app_state()
        if current_package is None or app_state is None:
            return None
        return (
            current_package,
            app_state.resource_manager,
            app_state.package_index_manager,
        )

    # --------------------------------------------------------------------- Current todo
    def build_current_todo_context(self) -> CurrentTodoContext:
        selected_todo_id = get_selected_todo_id_from_tree(self.host.tree)
        return CurrentTodoContext(
            selected_todo_id=selected_todo_id,
            current_todo_id=self.host.current_todo_id or "",
            current_detail_info=self.host.current_detail_info,
            todo_map=self.host.tree_manager.todo_map,
            todos=self.host.tree_manager.todos,
            find_first_todo_for_graph=self.host.find_first_todo_for_graph,
            get_item_by_id=self.host.tree_manager.get_item_by_id,
        )

    def resolve_current_leaf_todo(self) -> Optional["TodoItem"]:
        return resolve_current_todo_for_leaf(self.build_current_todo_context())

    # --------------------------------------------------------------------- Editor navigation
    def open_graph_in_editor(self, graph_id: str, graph_data: dict, container: object) -> None:
        main_window = self.get_main_window()
        if main_window is None:
            return
        todo_id = self.host.current_todo_id or ""
        detail_info = self.host.current_detail_info or {}
        todo_title = ""
        if todo_id:
            current_todo = self.host._get_todo_by_id(todo_id)
            todo_title = current_todo.title if current_todo else ""
        if todo_id and isinstance(detail_info, dict):
            main_window.register_graph_editor_todo_context(todo_id, detail_info, todo_title)

        nav = main_window.nav_coordinator
        if nav is None:
            return

        # 若当前全局画布已加载的就是目标图：只切模式，不重复触发 open_graph 导致二次 load/fit。
        graph_controller = getattr(main_window, "graph_controller", None)
        current_graph_id = ""
        if graph_controller is not None:
            current_graph_id = str(getattr(graph_controller, "current_graph_id", "") or "")
        if current_graph_id and current_graph_id == str(graph_id):
            nav.switch_to_editor.emit()
            return

        # nav_coordinator.open_graph 是稳定入口（避免 graph_controller fallback）
        from PyQt6 import QtCore as _QtCore

        _QtCore.QTimer.singleShot(
            30,
            lambda: nav.open_graph.emit(graph_id, graph_data, container),
        )


