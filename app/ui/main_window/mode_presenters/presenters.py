"""所有 ViewMode 的 presenter 实现（进入模式副作用）。"""

from __future__ import annotations

from typing import Any

from PyQt6 import QtCore

from app.models.view_modes import ViewMode

from .requests import ModeEnterRequest


class BaseModePresenter:
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> str | None:  # noqa: D401
        """进入模式后的副作用处理。"""
        raise NotImplementedError


class GraphLibraryModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> str:
        _ = request
        main_window.property_panel.clear()

        main_window.graph_library_widget.reload()

        def _sync_graph_library_selection() -> None:
            selected_graph_id = main_window.graph_library_widget.get_selected_graph_id()
            if not selected_graph_id:
                main_window.graph_library_widget.ensure_default_selection()
                selected_graph_id = main_window.graph_library_widget.get_selected_graph_id()

            if not selected_graph_id:
                main_window.graph_property_panel.set_empty_state()
                if hasattr(main_window, "file_watcher_manager"):
                    main_window.file_watcher_manager.setup_file_watcher("")
                return

            current_panel_graph_id = getattr(
                main_window.graph_property_panel, "current_graph_id", None
            )
            if current_panel_graph_id != selected_graph_id:
                main_window._on_graph_library_selected(selected_graph_id)

        QtCore.QTimer.singleShot(0, _sync_graph_library_selection)
        return "graph_property"


class GraphEditorModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> str:
        _ = request
        main_window.property_panel.clear()

        # GRAPH_EDITOR 使用全局唯一的 GraphView，但中央堆叠页是 Host 容器：
        # 若画布之前被 TODO 预览“借用”到了任务清单页面，需要在进入编辑器时归还。
        graph_editor_canvas_host = getattr(main_window, "graph_editor_canvas_host", None)
        if graph_editor_canvas_host is not None and hasattr(graph_editor_canvas_host, "attach_view"):
            graph_editor_canvas_host.attach_view(main_window.app_state.graph_view)

        # 进入编辑器时：恢复右上角按钮为“前往执行”，并关闭 Todo 预览的 click-signals 模式。
        graph_view = main_window.app_state.graph_view
        if hasattr(graph_view, "enable_click_signals"):
            graph_view.enable_click_signals = False
        if hasattr(graph_view, "restore_all_opacity"):
            graph_view.restore_all_opacity()
        overlay_manager = getattr(graph_view, "overlay_manager", None)
        if overlay_manager is not None and hasattr(overlay_manager, "stop_all_animations"):
            overlay_manager.stop_all_animations()
        preview_panel = getattr(getattr(main_window, "todo_widget", None), "preview_panel", None)
        if preview_panel is not None and hasattr(preview_panel, "preview_edit_button"):
            preview_panel.preview_edit_button.setVisible(False)
        if hasattr(main_window, "graph_editor_todo_button") and main_window.graph_editor_todo_button:
            graph_view.set_extra_top_right_button(main_window.graph_editor_todo_button)

        if main_window.graph_controller.current_graph_id:
            main_window.graph_property_panel.set_graph(main_window.graph_controller.current_graph_id)
        else:
            main_window.graph_property_panel.set_empty_state()

        # 确保图编辑器右上角“前往执行”按钮在任何进入 GRAPH_EDITOR 的路径下都能正确显示。
        # 说明：按钮初始为隐藏态，且旧逻辑主要依赖“图加载完成”事件触发可见性更新；
        # 当出现“仅切模式但不触发重新加载”的路径（例如重复打开当前图）时，会导致按钮保持隐藏。
        main_window._update_graph_editor_todo_button_visibility()
        return "graph_property"


class CompositeModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> str:
        _ = request
        if main_window.composite_widget is None:
            from app.ui.composite.composite_node_manager_widget import (
                CompositeNodeManagerWidget as _CompositeNodeManagerWidget,
            )

            main_window.composite_widget = _CompositeNodeManagerWidget(
                main_window.app_state.workspace_path,
                main_window.app_state.node_library,
                resource_manager=main_window.app_state.resource_manager,
                package_index_manager=main_window.app_state.package_index_manager,
            )
            main_window.composite_widget.composite_library_updated.connect(
                main_window._on_composite_library_updated
            )
            main_window.composite_widget.composite_selected.connect(main_window._on_composite_selected)

            idx = ViewMode.COMPOSITE.value
            main_window.central_stack.removeWidget(main_window._composite_placeholder)
            main_window.central_stack.insertWidget(idx, main_window.composite_widget)
            main_window.central_stack.setCurrentIndex(ViewMode.COMPOSITE.value)

            main_window.composite_property_panel.set_composite_widget(main_window.composite_widget)
            main_window.composite_pin_panel.set_composite_widget(main_window.composite_widget)

        # 进入复合节点页时同步一次当前存档上下文，保证左侧列表始终与顶部存档选择一致。
        set_context = getattr(main_window.composite_widget, "set_context", None)
        if callable(set_context):
            current_package_id = getattr(main_window.package_controller, "current_package_id", None)
            current_package_index = getattr(main_window.package_controller, "current_package_index", None)
            set_context(current_package_id, current_package_index)

        main_window.property_panel.clear()

        current_composite = main_window.composite_widget.get_current_composite()
        if current_composite:
            main_window.composite_property_panel.load_composite(current_composite)
            main_window.composite_pin_panel.load_composite(current_composite)
        else:
            main_window.composite_property_panel.clear()
            main_window.composite_pin_panel.clear()

        return "composite_pins"


class ValidationModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> str | None:
        _ = request
        main_window.property_panel.clear()
        # 注意：进入“验证”模式不再默认触发一次验证，避免用户仅查看历史结果时产生额外耗时。
        # 验证由用户显式触发：面板按钮/快捷键（F5）等入口。
        return "validation_detail"


class PackagesModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> None:
        _ = request
        main_window.property_panel.clear()

        main_window.package_library_widget.refresh()
        return None


class TodoModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> None:
        _ = request
        main_window.property_panel.clear()

        main_window._refresh_todo_list()
        return None


class ManagementModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> None:
        _ = request
        main_window.property_panel.clear()

        selection = main_window._get_management_current_selection()
        section_key = selection[0] if selection is not None else None
        has_selection = bool(selection and selection[1])

        main_window.right_panel.apply_management_selection(section_key, has_selection=has_selection)

        # 进入管理模式时主动刷新一次专用面板，避免“已有选中但未触发 selection_changed”导致右侧上下文落后。
        main_window._update_signal_property_panel_for_selection(selection)
        main_window._update_struct_property_panel_for_selection(selection)
        main_window._update_main_camera_panel_for_selection(selection)
        main_window._update_peripheral_system_panel_for_selection(selection)
        main_window._update_equipment_entry_panel_for_selection(selection)
        main_window._update_equipment_tag_panel_for_selection(selection)
        main_window._update_equipment_type_panel_for_selection(selection)
        return None


class TemplateModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> str | None:
        _ = request
        if hasattr(main_window.property_panel, "set_read_only"):
            main_window.property_panel.set_read_only(False)
        main_window.template_widget.refresh_templates()
        main_window.right_panel.ensure_visible(
            "property",
            visible=bool(main_window.property_panel.isEnabled()),
        )
        return "property"


class PlacementModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> str | None:
        _ = request
        if hasattr(main_window.property_panel, "set_read_only"):
            main_window.property_panel.set_read_only(False)
        main_window.placement_widget._rebuild_instances()
        main_window.right_panel.ensure_visible(
            "property",
            visible=bool(main_window.property_panel.isEnabled()),
        )
        return "property"


class CombatModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> None:
        main_window.property_panel.clear()

        from app.ui.graph.library_pages.library_scaffold import LibrarySelection

        def _normalize_combat_selection(selection: object | None) -> tuple[str, str] | None:
            if not isinstance(selection, LibrarySelection):
                return None
            if selection.kind != "combat":
                return None
            item_id = selection.id
            if not item_id:
                return None
            section_key = ""
            if isinstance(selection.context, dict):
                raw_section_key = selection.context.get("section_key")
                if isinstance(raw_section_key, str):
                    section_key = raw_section_key
            if not section_key:
                return None
            return (section_key, item_id)

        selection_before: tuple[str, str] | None = None
        get_selection = getattr(main_window.combat_widget, "get_selection", None)
        if callable(get_selection):
            selection_before = _normalize_combat_selection(get_selection())

        consume_pending = getattr(main_window, "_consume_pending_combat_selection", None)
        if callable(consume_pending):
            pending_selection = consume_pending()
            if pending_selection is not None:
                section_key, item_id = pending_selection
                if section_key and item_id:
                    if selection_before is None:
                        set_selection = getattr(main_window.combat_widget, "set_selection", None)
                        if callable(set_selection):
                            set_selection(
                                LibrarySelection(
                                    kind="combat",
                                    id=item_id,
                                    context={"section_key": section_key},
                                )
                            )

        ensure_default_selection = getattr(main_window.combat_widget, "ensure_default_selection", None)
        if callable(ensure_default_selection):
            ensure_default_selection()

        selection_after: tuple[str, str] | None = None
        if callable(get_selection):
            selection_after = _normalize_combat_selection(get_selection())

        # 若模式切回时选中未变化，库页不会再发 selection_changed；此处显式同步右侧详情面板。
        if selection_after is not None and selection_after == selection_before:
            section_key, item_id = selection_after
            if section_key == "player_template":
                main_window._on_player_template_selected(item_id)
            elif section_key == "player_class":
                main_window._on_player_class_selected(item_id)
            elif section_key == "skill":
                main_window._on_skill_selected(item_id)
            elif section_key == "item":
                main_window._on_item_selected(item_id)

        _ = request
        return None


