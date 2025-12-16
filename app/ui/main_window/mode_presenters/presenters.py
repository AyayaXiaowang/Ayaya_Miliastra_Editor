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
        main_window._ensure_property_tab_visible(False)
        main_window._ensure_management_property_tab_visible(False)
        main_window._remove_ui_settings_tab()

        main_window.graph_library_widget.refresh()

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
        main_window._ensure_property_tab_visible(False)
        main_window._ensure_management_property_tab_visible(False)
        main_window._remove_ui_settings_tab()

        if main_window.graph_controller.current_graph_id:
            main_window.graph_property_panel.set_graph(main_window.graph_controller.current_graph_id)
        else:
            main_window.graph_property_panel.set_empty_state()
        return "graph_property"


class CompositeModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> str:
        _ = request
        if main_window.composite_widget is None:
            from app.ui.composite.composite_node_manager_widget import (
                CompositeNodeManagerWidget as _CompositeNodeManagerWidget,
            )

            main_window.composite_widget = _CompositeNodeManagerWidget(
                main_window.workspace_path,
                main_window.library,
                resource_manager=main_window.resource_manager,
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

        main_window.property_panel.clear()
        main_window._ensure_property_tab_visible(False)
        main_window._ensure_management_property_tab_visible(False)
        main_window._remove_ui_settings_tab()

        current_composite = main_window.composite_widget.get_current_composite()
        if current_composite:
            main_window.composite_property_panel.load_composite(current_composite)
            main_window.composite_pin_panel.load_composite(current_composite)
        else:
            main_window.composite_property_panel.clear()
            main_window.composite_pin_panel.clear()

        return "composite_pins"


class ValidationModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> None:
        _ = request
        main_window.property_panel.clear()
        main_window._ensure_property_tab_visible(False)
        main_window._ensure_management_property_tab_visible(False)
        main_window._remove_ui_settings_tab()

        main_window._trigger_validation()
        return None


class PackagesModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> None:
        _ = request
        main_window.property_panel.clear()
        main_window._ensure_property_tab_visible(False)
        main_window._ensure_management_property_tab_visible(False)
        main_window._remove_ui_settings_tab()

        main_window.package_library_widget.refresh()
        return None


class TodoModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> None:
        _ = request
        main_window.property_panel.clear()
        main_window._ensure_property_tab_visible(False)
        main_window._ensure_management_property_tab_visible(False)
        main_window._remove_ui_settings_tab()

        main_window._refresh_todo_list()
        return None


class ManagementModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> None:
        _ = request
        main_window.property_panel.clear()
        main_window._ensure_property_tab_visible(False)
        main_window._ensure_management_property_tab_visible(False)

        policy = getattr(main_window, "right_panel_policy", None)
        apply_method = getattr(policy, "apply_management_section", None)
        if callable(apply_method):
            apply_method(None)

        selection = main_window._get_management_current_selection()
        has_selection = bool(selection and selection[1])
        main_window._update_signal_property_panel_for_selection(has_selection)
        main_window._update_struct_property_panel_for_selection(has_selection)
        return None


class TemplateModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> str | None:
        _ = request
        if hasattr(main_window.property_panel, "set_read_only"):
            main_window.property_panel.set_read_only(False)
        main_window.template_widget.refresh_templates()
        main_window._ensure_property_tab_visible(main_window.property_panel.isEnabled())
        main_window._remove_ui_settings_tab()
        main_window._ensure_management_property_tab_visible(False)
        return "property"


class PlacementModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> str | None:
        _ = request
        if hasattr(main_window.property_panel, "set_read_only"):
            main_window.property_panel.set_read_only(False)
        main_window.placement_widget._rebuild_instances()
        main_window._ensure_property_tab_visible(main_window.property_panel.isEnabled())
        main_window._remove_ui_settings_tab()
        main_window._ensure_management_property_tab_visible(False)
        return "property"


class CombatModePresenter(BaseModePresenter):
    def enter(self, main_window: Any, *, request: ModeEnterRequest) -> None:
        main_window.property_panel.clear()
        main_window._ensure_property_tab_visible(False)
        main_window._ensure_management_property_tab_visible(False)
        main_window._remove_ui_settings_tab()

        existing_selection = None
        get_selection_before = getattr(main_window.combat_widget, "get_current_selection", None)
        if callable(get_selection_before):
            existing_selection = get_selection_before()

        consume_pending = getattr(main_window, "_consume_pending_combat_selection", None)
        if callable(consume_pending):
            pending_selection = consume_pending()
            if pending_selection is not None:
                section_key, item_id = pending_selection
                if section_key and item_id:
                    if not existing_selection or not existing_selection[1]:
                        from app.ui.graph.library_pages.library_scaffold import LibrarySelection

                        selection = LibrarySelection(
                            kind="combat",
                            id=item_id,
                            context={"section_key": section_key},
                        )
                        set_selection = getattr(main_window.combat_widget, "set_selection", None)
                        if callable(set_selection):
                            set_selection(selection)

        ensure_default_selection = getattr(main_window.combat_widget, "ensure_default_selection", None)
        if callable(ensure_default_selection):
            ensure_default_selection()

        get_selection = getattr(main_window.combat_widget, "get_current_selection", None)
        if callable(get_selection):
            current_selection = get_selection()
            if current_selection is not None:
                section_key, item_id = current_selection
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


