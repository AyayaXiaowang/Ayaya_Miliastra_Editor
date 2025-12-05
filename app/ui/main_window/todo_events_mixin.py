"""任务清单与图编辑器联动相关的事件处理 Mixin"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt6 import QtCore, QtWidgets

from ui.graph.graph_view.top_right.controls_manager import TopRightControlsManager
from app.models.todo_generator import TodoGenerator
from app.models import TodoItem
from app.ui.todo.current_todo_resolver import build_context_from_host


class TodoEventsMixin:
    """负责任务清单刷新、勾选状态变更，以及与图编辑器联动的事件处理逻辑。"""

    # === 图编辑器右上角按钮与上下文 ===

    def register_graph_editor_todo_context(
        self,
        todo_id: str,
        detail_info: Dict[str, Any],
        todo_title: str = "",
    ) -> None:
        """记录从任务清单跳转到图编辑器的上下文，供编辑页面执行按钮使用。"""
        if not todo_id or not isinstance(detail_info, dict):
            self._graph_editor_todo_context = None
            self._update_graph_editor_todo_button_visibility()
            return

        snapshot = dict(detail_info)
        stored_title = todo_title or snapshot.get("title", "")

        self._graph_editor_todo_context = {
            "todo_id": todo_id,
            "detail_info": snapshot,
            "title": stored_title,
        }
        self._update_graph_editor_todo_button_visibility()

    def _on_graph_editor_execute_from_todo(self) -> None:
        """编辑器右上角按钮：跳回任务清单并定位关联步骤。"""
        context: Optional[Dict[str, Any]] = getattr(self, "_graph_editor_todo_context", None)
        if not context:
            return

        todo_id = context.get("todo_id")
        if not todo_id:
            return

        detail_info = context.get("detail_info") or {}
        self._navigate_to_mode("todo")

        def _jump_back() -> None:
            if hasattr(self, "todo_widget") and self.todo_widget:
                self.todo_widget.focus_task_from_external(todo_id, detail_info)

        QtCore.QTimer.singleShot(160, _jump_back)

    def _update_graph_editor_todo_button_visibility(self) -> None:
        """根据上下文与当前图状态，更新编辑器执行按钮的可见性和文案。"""
        button = getattr(self, "graph_editor_todo_button", None)
        if button is None or not hasattr(self, "graph_controller"):
            return

        context: Optional[Dict[str, Any]] = getattr(self, "_graph_editor_todo_context", None)
        should_show = False
        button_label = "前往执行"

        if context and isinstance(context, dict):
            detail_info = context.get("detail_info") or {}
            context_graph_id = str(detail_info.get("graph_id") or "")
            current_graph_id = str(self.graph_controller.current_graph_id or "")
            should_show = bool(
                context_graph_id and current_graph_id and context_graph_id == current_graph_id
            )

        button.setText(button_label)
        button.setVisible(should_show)

        if hasattr(self, "view") and isinstance(self.view, QtWidgets.QWidget):
            TopRightControlsManager.update_position(self.view)

    def _ensure_todo_data_loaded(self) -> None:
        """若任务清单尚未加载，自动生成一次数据供上下文匹配使用。"""
        if not hasattr(self, "todo_widget") or not self.todo_widget:
            return
        if self.todo_widget.has_loaded_todos():
            return
        if not hasattr(self, "package_controller") or not self.package_controller.current_package:
            return
        self._refresh_todo_list()

    def _ensure_todo_context_for_graph(self, graph_id: str) -> None:
        """当直接从其它页面打开图时，尝试匹配到任务清单中的步骤。"""
        if not graph_id or not hasattr(self, "todo_widget") or not self.todo_widget:
            return

        current_ctx: Optional[Dict[str, Any]] = getattr(self, "_graph_editor_todo_context", None)
        current_graph = ""
        if current_ctx:
            current_graph = str((current_ctx.get("detail_info") or {}).get("graph_id") or "")
        if current_ctx and current_graph == str(graph_id):
            return

        candidate = self.todo_widget.find_first_todo_for_graph(graph_id)
        if candidate is None:
            if current_ctx and current_graph == str(graph_id):
                self._graph_editor_todo_context = None
            return

        self.register_graph_editor_todo_context(
            candidate.todo_id,
            candidate.detail_info,
            candidate.title,
        )

    # === 任务清单 ===

    def _refresh_todo_list(self) -> None:
        """刷新任务清单"""
        # 在刷新前尽量记录一次任务清单上下文，供刷新后恢复选中与右侧联动使用。
        previous_selected_id: str = ""
        previous_current_id: str = ""
        previous_detail_info: Dict[str, Any] | None = None
        previous_graph_id: str = ""

        todo_widget = getattr(self, "todo_widget", None)
        if todo_widget is not None and getattr(todo_widget, "has_loaded_todos", None):
            if todo_widget.has_loaded_todos():
                context = build_context_from_host(todo_widget)
                previous_selected_id = context.selected_todo_id or ""
                previous_current_id = context.current_todo_id or ""
                if context.current_detail_info:
                    previous_detail_info = dict(context.current_detail_info)
                    graph_identifier = previous_detail_info.get("graph_id")
                    if graph_identifier is not None:
                        previous_graph_id = str(graph_identifier)

        package = self.package_controller.current_package
        package_id = getattr(self.package_controller, "current_package_id", "")
        package_type_name = type(package).__name__ if package is not None else "None"
        print(
            f"[TODO-REFRESH] 开始刷新任务清单: "
            f"package_id={package_id!r}, package_type={package_type_name}"
        )

        if not package:
            print("[TODO-REFRESH] 当前没有可用的存档（current_package 为空），跳过任务生成")
            return

        generator = TodoGenerator(package, self.resource_manager)
        todos = generator.generate_todos()
        print(f"[TODO-REFRESH] 任务生成完成，本次共生成 {len(todos)} 条 TodoItem")

        self.todo_widget.load_todos(todos, package.todo_states)

        # 刷新后尝试恢复到刷新前最接近的任务上下文：
        # 1) 优先尝试使用原选中项 / current_todo_id 的 todo_id；
        # 2) 退回到 detail_info 全量匹配；
        # 3) 最后按 graph_id 在新列表中择优选取一个 Todo（通常为叶子步骤）。
        if todo_widget is None:
            return

        has_previous_context = bool(
            previous_selected_id or previous_current_id or previous_detail_info or previous_graph_id
        )
        if not has_previous_context:
            return

        refreshed_context = build_context_from_host(todo_widget)
        todo_map_after = refreshed_context.todo_map
        todos_after = refreshed_context.todos

        resolved_todo: Optional[TodoItem] = None

        # 1) todo_id 直接命中（选中项优先，其次 current_todo_id）
        for candidate_id in (previous_selected_id, previous_current_id):
            if candidate_id and candidate_id in todo_map_after:
                resolved_todo = todo_map_after[candidate_id]
                break

        # 2) detail_info 全量匹配
        if resolved_todo is None and previous_detail_info is not None:
            for candidate in todos_after:
                if candidate.detail_info == previous_detail_info:
                    resolved_todo = candidate
                    break

        # 3) 根据 graph_id 查找该图下一个合理的 Todo（通常为叶子步骤）
        if resolved_todo is None and previous_graph_id:
            find_first = getattr(todo_widget, "find_first_todo_for_graph", None)
            if callable(find_first):
                fallback = find_first(previous_graph_id)
                if fallback is not None:
                    resolved_todo = fallback

        # 找到合适的 Todo 后，通过 TodoListWidget 提供的外部入口恢复选中与右侧详情/预览。
        if resolved_todo is not None and hasattr(todo_widget, "focus_task_from_external"):
            todo_widget.focus_task_from_external(
                resolved_todo.todo_id,
                resolved_todo.detail_info,
            )

    def _on_todo_checked(self, todo_id: str, checked: bool) -> None:
        """任务勾选状态改变"""
        package = self.package_controller.current_package
        if not package:
            return
        package.todo_states[todo_id] = checked

        # 标记当前存档存在未保存的 Todo 进度变化：
        # - 勾选操作只更新内存中的 todo_states 与 UI 树三态；
        # - 实际落盘仍交由工具栏“保存”按钮或窗口关闭流程统一处理，避免在频繁勾选时
        #   反复触发资源保存与 FileWatcher 导致的整表刷新。
        if hasattr(self, "_on_save_status_changed"):
            self._on_save_status_changed("unsaved")

    def on_todo_selection_changed(self, todo: TodoItem) -> None:
        """任务清单选中项变化时，根据任务类型在右侧展示只读属性面板。

        设计约定：
        - 模板/实例类任务在任务清单模式下同步到右侧元件属性面板，面板以只读方式展示；
        - 其他任务不干预属性面板标签，只保留执行监控等模式自带标签；
        - 离开任务清单模式后，由模式切换逻辑恢复属性面板的可编辑状态。
        """
        if not todo or not getattr(self, "package_controller", None):
            return

        # 优先根据步骤类型控制“执行监控”标签的显示：仅在节点图相关步骤下展示
        self._update_execution_monitor_tab_for_todo(todo)

        package = self.package_controller.current_package
        if not package or not hasattr(self, "property_panel"):
            return

        detail_info = todo.detail_info or {}
        detail_type = str(detail_info.get("type", ""))
        task_type = str(todo.task_type or "")

        is_template_task = task_type == "template" or detail_type == "template"
        is_instance_task = task_type == "instance" or detail_type == "instance"

        # 仅在模板/实例相关任务下展示属性面板
        if not (is_template_task or is_instance_task):
            # 若此前因 Todo 选中而打开过属性面板，这里不强制关闭，仅在模式切换时统一回收
            return

        # 切换到只读模式，防止在任务清单页面误修改真实数据
        if hasattr(self.property_panel, "set_read_only"):
            self.property_panel.set_read_only(True)

        if is_template_task:
            template_id = detail_info.get("template_id") or todo.target_id
            if template_id:
                self.property_panel.set_template(package, str(template_id))
        elif is_instance_task:
            instance_id = detail_info.get("instance_id") or todo.target_id
            if instance_id:
                self.property_panel.set_instance(package, str(instance_id))

        # 在任务清单模式下按需将“属性”标签插入右侧标签页
        if hasattr(self, "_ensure_property_tab_visible"):
            self._ensure_property_tab_visible(True)

        if hasattr(self, "_schedule_ui_session_state_save"):
            self._schedule_ui_session_state_save()

    def _update_execution_monitor_tab_for_todo(self, todo: TodoItem) -> None:
        """根据 Todo 步骤类型按需显示/隐藏右侧“执行监控”标签页。

        规则：
        - 仅当步骤属于节点图相关类型时显示：
          - 模板图根: template_graph_root
          - 事件流根: event_flow_root
          - 复合节点步骤: 以 \"composite_\" 开头
          - 节点图叶子步骤: 以 \"graph\" 开头，且排除图根/变量总表
        - 其他步骤（如纯模板属性、实例属性、管理类任务）不显示执行监控标签。
        """
        if not hasattr(self, "side_tab") or not hasattr(self, "execution_monitor_panel"):
            return
        side_tab = self.side_tab
        monitor_panel = self.execution_monitor_panel

        detail_info = todo.detail_info or {}
        detail_type = str(detail_info.get("type", ""))

        is_template_graph_root = detail_type == "template_graph_root"
        is_event_flow_root = detail_type == "event_flow_root"
        is_composite_step = detail_type.startswith("composite_")
        is_leaf_graph_step = (
            detail_type.startswith("graph")
            and not is_template_graph_root
            and not is_event_flow_root
            and detail_type != "graph_variables_table"
        )
        should_show_monitor = (
            is_template_graph_root
            or is_event_flow_root
            or is_composite_step
            or is_leaf_graph_step
        )

        current_index = side_tab.indexOf(monitor_panel)

        if should_show_monitor:
            if current_index == -1:
                tab_title = "执行监控"
                if hasattr(self, "_tab_title_for_id"):
                    tab_title = self._tab_title_for_id("execution_monitor")
                side_tab.addTab(monitor_panel, tab_title)
            if hasattr(self, "_update_right_panel_visibility"):
                self._update_right_panel_visibility()
            return

        if current_index != -1:
            if side_tab.currentWidget() is monitor_panel and side_tab.count() > 1:
                side_tab.setCurrentIndex(0)
            side_tab.removeTab(current_index)
            if hasattr(self, "_update_right_panel_visibility"):
                self._update_right_panel_visibility()
