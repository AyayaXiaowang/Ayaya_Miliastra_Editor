from __future__ import annotations

from typing import Any

from app.ui.main_window.features.feature_protocol import MainWindowFeature
from app.ui.main_window.wiring import (
    bind_graph_library_page,
    bind_management_page,
    bind_package_library_page,
    bind_todo_page,
    bind_validation_page,
)


class CentralPagesAssemblyFeature(MainWindowFeature):
    """中央页面装配 Feature：集中所有页面信号连接与页面级 binder 调用。"""

    feature_id = "central_pages_assembly"

    def install(self, *, main_window: Any) -> None:
        connect_optional_signal = getattr(main_window, "_connect_optional_signal", None)
        if not callable(connect_optional_signal):
            raise RuntimeError("CentralPagesAssemblyFeature.install 需要 main_window._connect_optional_signal 可调用")

        nav_coordinator = getattr(main_window, "nav_coordinator", None)

        # === Template / Placement / Combat：基础选中与 data_changed ===
        template_widget = getattr(main_window, "template_widget", None)
        if template_widget is not None:
            template_widget.template_selected.connect(main_window._on_template_selected)
            connect_optional_signal(template_widget, "data_changed", main_window._on_library_page_data_changed)

        placement_widget = getattr(main_window, "placement_widget", None)
        if placement_widget is not None:
            placement_widget.instance_selected.connect(main_window._on_instance_selected)
            placement_widget.level_entity_selected.connect(main_window._on_level_entity_selected)
            connect_optional_signal(placement_widget, "data_changed", main_window._on_library_page_data_changed)

        combat_widget = getattr(main_window, "combat_widget", None)
        if combat_widget is not None:
            connect_optional_signal(combat_widget, "player_template_selected", main_window._on_player_template_selected)
            connect_optional_signal(combat_widget, "player_class_selected", main_window._on_player_class_selected)
            connect_optional_signal(combat_widget, "skill_selected", main_window._on_skill_selected)
            connect_optional_signal(combat_widget, "item_selected", main_window._on_item_selected)
            connect_optional_signal(combat_widget, "data_changed", main_window._on_library_page_data_changed)

        # === Management：页面级 binder + active section ===
        management_widget = getattr(main_window, "management_widget", None)
        if management_widget is not None:
            connect_optional_signal(management_widget, "data_changed", main_window._on_library_page_data_changed)
            connect_optional_signal(
                management_widget,
                "active_section_changed",
                main_window._on_management_section_changed,
            )
            if nav_coordinator is not None:
                bind_management_page(management_widget=management_widget, nav_coordinator=nav_coordinator)

        # === Todo：注入 main_window/resource_manager + 页面级 binder ===
        todo_widget = getattr(main_window, "todo_widget", None)
        if todo_widget is not None:
            todo_widget.main_window = main_window
            if hasattr(main_window, "resource_manager"):
                todo_widget.resource_manager = main_window.resource_manager
            if nav_coordinator is not None:
                bind_todo_page(
                    todo_widget=todo_widget,
                    nav_coordinator=nav_coordinator,
                    on_todo_checked=main_window._on_todo_checked,
                )

        # === Graph library：列表信号 + 页面级 binder ===
        graph_library_widget = getattr(main_window, "graph_library_widget", None)
        if graph_library_widget is not None:
            graph_library_widget.graph_selected.connect(main_window._on_graph_library_selected)
            graph_library_widget.graph_double_clicked.connect(main_window._on_graph_library_double_clicked)
            if nav_coordinator is not None:
                bind_graph_library_page(graph_library_widget=graph_library_widget, nav_coordinator=nav_coordinator)

        # === Validation：页面级 binder ===
        validation_panel = getattr(main_window, "validation_panel", None)
        if validation_panel is not None and nav_coordinator is not None:
            bind_validation_page(validation_panel=validation_panel, nav_coordinator=nav_coordinator)

        # === Package library：packages_changed + 页面级 binder + 若干可选信号 ===
        package_library_widget = getattr(main_window, "package_library_widget", None)
        if package_library_widget is not None:
            package_library_widget.packages_changed.connect(main_window._refresh_package_list)
            connect_optional_signal(package_library_widget, "resource_activated", main_window._on_package_resource_activated)
            connect_optional_signal(
                package_library_widget,
                "management_resource_activated",
                main_window._on_package_management_resource_activated,
            )
            connect_optional_signal(
                package_library_widget,
                "management_item_requested",
                main_window._on_package_management_item_requested,
            )
            connect_optional_signal(
                package_library_widget,
                "graph_double_clicked",
                main_window._on_graph_library_double_clicked,
            )
            if nav_coordinator is not None:
                bind_package_library_page(
                    package_library_widget=package_library_widget,
                    nav_coordinator=nav_coordinator,
                )


