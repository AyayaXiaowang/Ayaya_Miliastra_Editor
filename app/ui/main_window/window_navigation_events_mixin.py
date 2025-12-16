"""导航切换、窗口状态与验证相关的事件处理 Mixin"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui
from typing import Any, Dict, Optional

from app.ui.foundation.toast_notification import ToastNotification
from app.ui.dialogs.settings_dialog import SettingsDialog
from app.models.view_modes import ViewMode
from engine.validate.comprehensive_validator import ComprehensiveValidator
from engine.configs.resource_types import ResourceType
from app.ui.graph.library_pages.library_scaffold import LibrarySelection
from app.runtime.ui_session_state import load_last_session_state, save_last_session_state
from app.ui.todo.current_todo_resolver import build_context_from_host


class WindowAndNavigationEventsMixin:
    """负责导航切换、窗口标题/保存状态、验证与设置等通用事件处理逻辑。"""

    # === 窗口标题与状态 ===

    def _update_window_title(self, title: str) -> None:
        """更新窗口标题"""
        from app.ui.main_window.main_window import APP_TITLE

        self.setWindowTitle(f"{APP_TITLE} - {title}")

    def _refresh_save_status_label_for_mode(self, view_mode: ViewMode) -> None:
        """根据当前视图模式刷新右上角保存状态提示文案。"""
        if not hasattr(self, "save_status_label"):
            return

        # 节点图库 / 复合节点页面：固定提示为只读
        if view_mode in (ViewMode.GRAPH_LIBRARY, ViewMode.COMPOSITE):
            self.save_status_label.setText("当前页面不允许修改")
            self.save_status_label.setProperty("status", "readonly")
            self.save_status_label.style().unpolish(self.save_status_label)
            self.save_status_label.style().polish(self.save_status_label)
            return

        # 其他模式：根据最近一次保存状态恢复提示文案
        last_status = getattr(self, "_last_save_status", "saved")
        status_text_map = {
            "saved": "✓ 已保存",
            "unsaved": "● 未保存",
            "saving": "⟳ 保存中...",
        }
        self.save_status_label.setText(status_text_map.get(last_status, "已保存"))
        self.save_status_label.setProperty("status", last_status)
        self.save_status_label.style().unpolish(self.save_status_label)
        self.save_status_label.style().polish(self.save_status_label)

    # === UI 会话状态持久化 ===

    def _serialize_library_selection(self, selection: Optional[LibrarySelection]) -> Optional[Dict[str, Any]]:
        """将 LibrarySelection 转换为可 JSON 序列化的简单字典。"""
        if selection is None:
            return None
        selection_context: Optional[Dict[str, Any]]
        if isinstance(selection.context, dict):
            selection_context = selection.context
        else:
            selection_context = None
        return {
            "kind": selection.kind,
            "id": selection.id,
            "context": selection_context,
        }

    def _deserialize_library_selection(self, payload: Dict[str, Any]) -> Optional[LibrarySelection]:
        """从持久化字典还原 LibrarySelection。"""
        if not isinstance(payload, dict):
            return None
        kind_value = payload.get("kind")
        identifier_value = payload.get("id")
        if not isinstance(kind_value, str) or not isinstance(identifier_value, str):
            return None
        context_value = payload.get("context")
        if context_value is not None and not isinstance(context_value, dict):
            context_value = None
        return LibrarySelection(
            kind=kind_value,
            id=identifier_value,
            context=context_value,
        )

    def _build_ui_session_state_payload(self) -> Dict[str, Any]:
        """采集当前主窗口的 UI 会话状态，供持久化使用。"""
        state_payload: Dict[str, Any] = {}

        current_view_mode: Optional[ViewMode] = None
        if hasattr(self, "central_stack"):
            mode_index = self.central_stack.currentIndex()
            current_view_mode = ViewMode.from_index(mode_index)
        if current_view_mode is not None:
            state_payload["view_mode"] = current_view_mode.to_string()

        if hasattr(self, "package_controller"):
            current_package_identifier = getattr(self.package_controller, "current_package_id", None)
            if isinstance(current_package_identifier, str) and current_package_identifier:
                state_payload["package_id"] = current_package_identifier

        selections: Dict[str, Any] = {}

        template_widget = getattr(self, "template_widget", None)
        if template_widget is not None and hasattr(template_widget, "get_selection"):
            template_selection = template_widget.get_selection()
            serialized_template = self._serialize_library_selection(template_selection)
            if serialized_template is not None:
                selections["template"] = serialized_template

        placement_widget = getattr(self, "placement_widget", None)
        if placement_widget is not None and hasattr(placement_widget, "get_selection"):
            placement_selection = placement_widget.get_selection()
            serialized_placement = self._serialize_library_selection(placement_selection)
            if serialized_placement is not None:
                selections["placement"] = serialized_placement

        combat_widget = getattr(self, "combat_widget", None)
        if combat_widget is not None and hasattr(combat_widget, "get_selection"):
            combat_selection = combat_widget.get_selection()
            serialized_combat = self._serialize_library_selection(combat_selection)
            if serialized_combat is not None:
                selections["combat"] = serialized_combat

        management_widget = getattr(self, "management_widget", None)
        if management_widget is not None and hasattr(management_widget, "get_selection"):
            management_selection = management_widget.get_selection()
            serialized_management = self._serialize_library_selection(management_selection)
            if serialized_management is not None:
                selections["management"] = serialized_management

        graph_library_widget = getattr(self, "graph_library_widget", None)
        if graph_library_widget is not None and hasattr(graph_library_widget, "get_selection"):
            graph_library_selection = graph_library_widget.get_selection()
            serialized_graph_library = self._serialize_library_selection(graph_library_selection)
            if serialized_graph_library is not None:
                selections["graph_library"] = serialized_graph_library

        package_library_widget = getattr(self, "package_library_widget", None)
        if package_library_widget is not None and hasattr(package_library_widget, "get_selection"):
            package_library_selection = package_library_widget.get_selection()
            serialized_package_library = self._serialize_library_selection(package_library_selection)
            if serialized_package_library is not None:
                selections["packages"] = serialized_package_library

        if selections:
            state_payload["selections"] = selections

        todo_widget = getattr(self, "todo_widget", None)
        if todo_widget is not None:
            todo_context = build_context_from_host(todo_widget)
            todo_state: Dict[str, Any] = {
                "selected_todo_id": todo_context.selected_todo_id or "",
                "current_todo_id": todo_context.current_todo_id or "",
                "current_detail_info": todo_context.current_detail_info,
            }
            state_payload["todo"] = todo_state

        graph_controller = getattr(self, "graph_controller", None)
        if graph_controller is not None:
            current_graph_identifier = getattr(graph_controller, "current_graph_id", None)
            if isinstance(current_graph_identifier, str) and current_graph_identifier:
                state_payload["graph_editor"] = {"graph_id": current_graph_identifier}

        state_payload["schema_version"] = 1
        return state_payload

    def _save_ui_session_state(self) -> None:
        """在窗口关闭前采集并持久化当前 UI 会话状态。"""
        workspace_path = getattr(self, "workspace_path", None)
        if workspace_path is None:
            return
        state_payload = self._build_ui_session_state_payload()
        save_last_session_state(workspace_path, state_payload)

    def _schedule_ui_session_state_save(self) -> None:
        """请求在短暂延迟后保存一次 UI 会话状态（轻量去抖）。"""
        workspace_path = getattr(self, "workspace_path", None)
        if workspace_path is None:
            return

        existing_timer = getattr(self, "_ui_session_state_timer", None)
        if not isinstance(existing_timer, QtCore.QTimer):
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)

            def _on_timeout() -> None:
                if hasattr(self, "_save_ui_session_state"):
                    self._save_ui_session_state()

            timer.timeout.connect(_on_timeout)
            setattr(self, "_ui_session_state_timer", timer)
            existing_timer = timer

        existing_timer.start(500)

    def _restore_ui_session_state(self) -> None:
        """在启动完成后尝试从磁盘恢复上一次 UI 会话状态。"""
        workspace_path = getattr(self, "workspace_path", None)
        if workspace_path is None:
            return

        loaded_state = load_last_session_state(workspace_path)
        if not isinstance(loaded_state, dict):
            return

        schema_version_value = loaded_state.get("schema_version")
        if schema_version_value != 1:
            return

        package_identifier_in_state = loaded_state.get("package_id")
        if isinstance(package_identifier_in_state, str) and package_identifier_in_state:
            package_controller = getattr(self, "package_controller", None)
            if package_controller is not None:
                current_package_identifier = getattr(package_controller, "current_package_id", None)
                if current_package_identifier != package_identifier_in_state:
                    package_controller.load_package(package_identifier_in_state)

        view_mode_identifier = loaded_state.get("view_mode")
        if isinstance(view_mode_identifier, str) and view_mode_identifier:
            self._restore_view_mode_from_state(view_mode_identifier, loaded_state)
        else:
            graph_editor_state = loaded_state.get("graph_editor")
            if isinstance(graph_editor_state, dict):
                self._restore_graph_editor_from_state(graph_editor_state)

    def _restore_view_mode_from_state(self, mode_identifier: str, full_state: Dict[str, Any]) -> None:
        """根据记录的视图模式和状态恢复主视图与选中上下文。"""
        target_view_mode = ViewMode.from_string(mode_identifier)
        if target_view_mode is None:
            return

        selection_map: Dict[str, Any]
        raw_selections = full_state.get("selections")
        if isinstance(raw_selections, dict):
            selection_map = raw_selections
        else:
            selection_map = {}

        if target_view_mode == ViewMode.TEMPLATE:
            self._navigate_to_mode("template")
            template_payload = selection_map.get("template")
            if isinstance(template_payload, dict):
                selection = self._deserialize_library_selection(template_payload)
                template_widget = getattr(self, "template_widget", None)
                if template_widget is not None and hasattr(template_widget, "set_selection"):
                    template_widget.set_selection(selection)
            return

        if target_view_mode == ViewMode.PLACEMENT:
            self._navigate_to_mode("placement")
            placement_payload = selection_map.get("placement")
            if isinstance(placement_payload, dict):
                selection = self._deserialize_library_selection(placement_payload)
                placement_widget = getattr(self, "placement_widget", None)
                if placement_widget is not None and hasattr(placement_widget, "set_selection"):
                    placement_widget.set_selection(selection)
            return

        if target_view_mode == ViewMode.COMBAT:
            self._navigate_to_mode("combat")
            combat_payload = selection_map.get("combat")
            if isinstance(combat_payload, dict):
                selection = self._deserialize_library_selection(combat_payload)
                combat_widget = getattr(self, "combat_widget", None)
                if combat_widget is not None and hasattr(combat_widget, "set_selection"):
                    combat_widget.set_selection(selection)
            return

        if target_view_mode == ViewMode.MANAGEMENT:
            self._navigate_to_mode("management")
            management_payload = selection_map.get("management")
            if isinstance(management_payload, dict):
                selection = self._deserialize_library_selection(management_payload)
                management_widget = getattr(self, "management_widget", None)
                if management_widget is not None and selection is not None:
                    section_key_value: Optional[str] = None
                    if isinstance(selection.context, dict):
                        raw_section_key = selection.context.get("section_key")
                        if isinstance(raw_section_key, str) and raw_section_key:
                            section_key_value = raw_section_key
                    if section_key_value:
                        focus_method = getattr(management_widget, "focus_section_and_item", None)
                        if callable(focus_method):
                            focus_method(section_key_value, selection.id)
                    elif hasattr(management_widget, "set_selection"):
                        management_widget.set_selection(selection)
            return

        if target_view_mode == ViewMode.TODO:
            self._navigate_to_mode("todo")
            todo_state = full_state.get("todo")
            if isinstance(todo_state, dict):
                self._restore_todo_page_from_state(todo_state)
            return

        if target_view_mode == ViewMode.GRAPH_LIBRARY:
            self._navigate_to_mode("graph_library")
            graph_library_payload = selection_map.get("graph_library")
            if isinstance(graph_library_payload, dict):
                selection = self._deserialize_library_selection(graph_library_payload)
                graph_library_widget = getattr(self, "graph_library_widget", None)
                if graph_library_widget is not None and hasattr(graph_library_widget, "set_selection"):
                    graph_library_widget.set_selection(selection)
            return

        if target_view_mode == ViewMode.PACKAGES:
            self._navigate_to_mode("packages")
            packages_payload = selection_map.get("packages")
            if isinstance(packages_payload, dict):
                selection = self._deserialize_library_selection(packages_payload)
                package_library_widget = getattr(self, "package_library_widget", None)
                if package_library_widget is not None and hasattr(package_library_widget, "set_selection"):
                    package_library_widget.set_selection(selection)
            return

        if target_view_mode == ViewMode.VALIDATION:
            self._navigate_to_mode("validation")
            return

        if target_view_mode == ViewMode.COMPOSITE:
            self._navigate_to_mode("composite")
            return

        if target_view_mode == ViewMode.GRAPH_EDITOR:
            graph_editor_state = full_state.get("graph_editor")
            if isinstance(graph_editor_state, dict):
                self._restore_graph_editor_from_state(graph_editor_state)
            else:
                self._navigate_to_mode("graph_editor")
            return

    def _restore_todo_page_from_state(self, todo_state: Dict[str, Any]) -> None:
        """在任务清单模式下，根据保存的上下文恢复当前任务选中与详情。"""
        todo_widget = getattr(self, "todo_widget", None)
        if todo_widget is None:
            return

        current_todo_identifier_value = todo_state.get("current_todo_id") or ""
        selected_todo_identifier_value = todo_state.get("selected_todo_id") or ""
        detail_information = todo_state.get("current_detail_info")

        todo_identifier_to_use = ""
        if isinstance(current_todo_identifier_value, str) and current_todo_identifier_value:
            todo_identifier_to_use = current_todo_identifier_value
        elif isinstance(selected_todo_identifier_value, str) and selected_todo_identifier_value:
            todo_identifier_to_use = selected_todo_identifier_value

        if not todo_identifier_to_use:
            return

        detail_payload: Optional[Dict[str, Any]]
        if isinstance(detail_information, dict):
            detail_payload = detail_information
        else:
            detail_payload = None

        if hasattr(todo_widget, "focus_task_from_external"):
            todo_widget.focus_task_from_external(todo_identifier_to_use, detail_payload)

    def _restore_graph_editor_from_state(self, graph_editor_state: Dict[str, Any]) -> None:
        """根据保存的 graph_id 重新在编辑器中打开对应节点图。"""
        graph_identifier_value = graph_editor_state.get("graph_id")
        if not isinstance(graph_identifier_value, str) or not graph_identifier_value:
            return
        resource_manager_candidate = getattr(self, "resource_manager", None)
        graph_controller_candidate = getattr(self, "graph_controller", None)
        if resource_manager_candidate is None or graph_controller_candidate is None:
            return

        graph_resource = resource_manager_candidate.load_resource(ResourceType.GRAPH, graph_identifier_value)
        if not isinstance(graph_resource, dict):
            return

        graph_data_payload = graph_resource.get("data")
        if not isinstance(graph_data_payload, dict):
            return

        graph_name_value = graph_resource.get("name")
        if isinstance(graph_name_value, str) and graph_name_value:
            graph_display_name = graph_name_value
        else:
            graph_display_name = graph_identifier_value

        graph_controller_candidate.open_independent_graph(
            graph_identifier_value,
            graph_resource,
            graph_display_name,
        )

    def _on_save_status_changed(self, status: str) -> None:
        """保存状态改变"""
        # 记录最近一次保存状态，便于离开只读页面后恢复提示
        self._last_save_status = status

        controller = getattr(self, "package_controller", None)
        if controller is not None:
            if status == "unsaved" and hasattr(controller, "mark_graph_dirty"):
                controller.mark_graph_dirty()
            elif status == "saved" and hasattr(controller, "clear_graph_dirty"):
                controller.clear_graph_dirty()

        if not hasattr(self, "save_status_label"):
            return

        current_mode = None
        if hasattr(self, "central_stack"):
            current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode in (ViewMode.GRAPH_LIBRARY, ViewMode.COMPOSITE):
            # 在节点图库与复合节点模式下，始终显示“当前页面不允许修改”
            self._refresh_save_status_label_for_mode(current_mode)
            return

        status_text_map = {
            "saved": "✓ 已保存",
            "unsaved": "● 未保存",
            "saving": "⟳ 保存中...",
        }
        self.save_status_label.setText(status_text_map.get(status, "已保存"))
        self.save_status_label.setProperty("status", status)
        self.save_status_label.style().unpolish(self.save_status_label)
        self.save_status_label.style().polish(self.save_status_label)

    # === 全局 Toast 通知 ===

    def _show_toast(self, message: str, toast_type: str) -> None:
        """显示 Toast 通知"""
        ToastNotification.show_message(self, message, toast_type)

    # === 导航与辅助跳转 ===

    def _navigate_to_mode(self, mode: str) -> None:
        """导航到指定模式

        如果是图编辑器，没有对应的左侧导航按钮；为达到一致体验，左侧高亮"节点图库"。
        """
        nav_mode = mode
        if mode == "graph_editor":
            nav_mode = "graph_library"

        self.nav_bar.set_current_mode(nav_mode)
        self._on_mode_changed(mode)

    def _on_management_section_changed(self, section_key: str) -> None:
        """管理面板左侧 section 选中变化时，根据当前 section 更新右侧相关标签。"""
        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode != ViewMode.MANAGEMENT:
            return

        # ViewState 记录当前 section（单一真源雏形）
        view_state = getattr(self, "view_state", None)
        management_state = getattr(view_state, "management", None) if view_state is not None else None
        if management_state is not None:
            setattr(management_state, "section_key", str(section_key))

        policy = getattr(self, "right_panel_policy", None)
        apply_method = getattr(policy, "apply_management_section", None)
        if callable(apply_method):
            apply_method(section_key)

    def _open_player_editor(self) -> None:
        """打开玩家编辑器（战斗预设页签内部）"""
        # 确保战斗预设页面的“玩家模板”标签被选中
        if hasattr(self, "combat_widget") and hasattr(self.combat_widget, "switch_to_player_editor"):
            self.combat_widget.switch_to_player_editor()
        elif hasattr(self, "combat_widget") and hasattr(self.combat_widget, "tabs"):
            self.combat_widget.tabs.setCurrentIndex(0)
        # 同时将右侧面板切换到玩家模板详情标签（如已挂载）
        if hasattr(self, "right_panel_registry"):
            self.right_panel_registry.switch_to("player_editor")

    # === 验证与设置 ===

    def _trigger_validation(self) -> None:
        """触发当前存档的验证流程"""
        package = self.package_controller.current_package
        if not package:
            self.validation_panel.clear()
            return

        validator = ComprehensiveValidator(package, self.resource_manager, verbose=False)
        issues = validator.validate_all()
        self.validation_panel.update_issues(issues)

    def _open_settings_dialog(self) -> None:
        """打开设置对话框并在需要时刷新任务清单"""
        dialog = SettingsDialog(self)
        dialog.exec()

        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode == ViewMode.TODO:
            self._refresh_todo_list()
            self._show_toast("已根据新设置刷新任务清单", "success")

    def _on_manual_refresh_resource_library(self) -> None:
        """手动刷新资源库（顶部工具栏“更新”按钮）。

        当选择“手动更新”模式或希望立刻查看外部工具对资源库的改动时，
        通过此入口重建资源索引并刷新各资源库相关视图。
        """
        if hasattr(self, "refresh_resource_library"):
            self.refresh_resource_library()
        self._show_toast("已根据磁盘最新内容刷新资源库", "info")

    # === 窗口关闭 ===

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """窗口关闭事件"""
        if hasattr(self, "_save_ui_session_state"):
            self._save_ui_session_state()
        self.file_watcher_manager.cleanup()
        self.package_controller.save_package()

        from engine.configs.settings import settings

        settings.save()
        event.accept()


