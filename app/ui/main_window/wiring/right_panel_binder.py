from __future__ import annotations

from typing import Any, Callable

from app.models import UiNavigationRequest


def bind_template_instance_panel(
    *,
    property_panel: Any,
    package_controller: Any,
    on_data_updated: Callable[[], None],
    on_graph_selected: Callable[..., None],
    on_template_package_membership_changed: Callable[..., None],
    on_instance_package_membership_changed: Callable[..., None],
) -> None:
    """绑定模板/实例属性面板信号，以及保存前 flush 回调。"""

    property_panel.data_updated.connect(on_data_updated)
    property_panel.graph_selected.connect(on_graph_selected)
    property_panel.template_package_membership_changed.connect(on_template_package_membership_changed)
    property_panel.instance_package_membership_changed.connect(on_instance_package_membership_changed)

    # 在保存存档前，通过 PackageController 回调刷新基础信息页中尚未通过去抖写回的编辑内容。
    if package_controller is not None:
        package_controller.flush_current_resource_panel = property_panel.flush_pending_changes


def bind_combat_panels(
    *,
    connect_optional_signal: Callable[[object, str, Callable[..., None]], None],
    player_editor_panel: Any,
    player_class_panel: Any,
    skill_panel: Any,
    item_panel: Any,
    on_immediate_persist_requested: Callable[..., None],
    on_player_editor_graph_selected: Callable[..., None],
) -> None:
    """绑定战斗预设相关右侧详情面板（玩家模板/职业/技能/道具）的信号。"""

    def _persist_combat_and_index() -> None:
        on_immediate_persist_requested(
            combat_dirty=True,
            index_dirty=True,
        )

    player_editor_panel.data_changed.connect(_persist_combat_and_index)
    player_class_panel.data_changed.connect(_persist_combat_and_index)
    skill_panel.data_changed.connect(_persist_combat_and_index)
    item_panel.data_changed.connect(_persist_combat_and_index)

    connect_optional_signal(player_editor_panel, "graph_selected", on_player_editor_graph_selected)
    connect_optional_signal(player_class_panel, "graph_selected", on_player_editor_graph_selected)
    connect_optional_signal(skill_panel, "graph_selected", on_player_editor_graph_selected)


def bind_graph_property_panel(
    *,
    graph_property_panel: Any,
    nav_coordinator: Any,
    graph_controller: Any,
    on_graph_updated_from_property: Callable[..., None],
    on_graph_package_membership_changed: Callable[..., None],
) -> None:
    """绑定右侧“图属性”面板信号。"""

    def _on_jump_to_reference(entity_type: str, entity_id: str, package_id: str) -> None:
        request = UiNavigationRequest.for_property_panel_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            package_id=package_id,
            origin="graph_property",
        )
        nav_coordinator.handle_request(request)

    graph_property_panel.jump_to_reference.connect(_on_jump_to_reference)
    graph_property_panel.graph_updated.connect(on_graph_updated_from_property)
    graph_property_panel.package_membership_changed.connect(on_graph_package_membership_changed)
    graph_property_panel.graph_editor_controller = graph_controller


def bind_composite_panels(
    *,
    composite_property_panel: Any,
    on_composite_package_membership_changed: Callable[..., None],
) -> None:
    """绑定复合节点右侧属性面板信号。"""
    composite_property_panel.package_membership_changed.connect(on_composite_package_membership_changed)


def bind_management_panels(
    *,
    connect_optional_signal: Callable[[object, str, Callable[..., None]], None],
    management_property_panel: Any,
    on_management_property_panel_membership_changed: Callable[..., None],
    equipment_entry_panel: Any,
    on_equipment_entry_package_membership_changed: Callable[..., None],
    equipment_tag_panel: Any,
    on_equipment_tag_package_membership_changed: Callable[..., None],
    equipment_type_panel: Any,
    on_equipment_type_package_membership_changed: Callable[..., None],
    peripheral_system_panel: Any,
    on_peripheral_system_panel_package_membership_changed: Callable[..., None],
    main_camera_panel: Any,
    on_main_camera_panel_package_membership_changed: Callable[..., None],
    signal_management_panel: Any,
    on_signal_property_panel_changed: Callable[..., None],
    on_signal_property_panel_package_membership_changed: Callable[..., None],
    struct_definition_panel: Any,
    on_struct_property_panel_struct_changed: Callable[..., None],
    on_struct_property_panel_membership_changed: Callable[..., None],
    on_management_edit_page_data_updated: Callable[..., None],
) -> None:
    """绑定管理模式相关右侧编辑/属性面板信号。"""

    connect_optional_signal(
        management_property_panel,
        "management_package_membership_changed",
        on_management_property_panel_membership_changed,
    )

    equipment_entry_panel.data_updated.connect(on_management_edit_page_data_updated)
    connect_optional_signal(
        equipment_entry_panel,
        "package_membership_changed",
        on_equipment_entry_package_membership_changed,
    )

    equipment_tag_panel.data_updated.connect(on_management_edit_page_data_updated)
    connect_optional_signal(
        equipment_tag_panel,
        "package_membership_changed",
        on_equipment_tag_package_membership_changed,
    )

    equipment_type_panel.data_updated.connect(on_management_edit_page_data_updated)
    connect_optional_signal(
        equipment_type_panel,
        "package_membership_changed",
        on_equipment_type_package_membership_changed,
    )

    peripheral_system_panel.data_updated.connect(on_management_edit_page_data_updated)
    connect_optional_signal(
        peripheral_system_panel,
        "system_package_membership_changed",
        on_peripheral_system_panel_package_membership_changed,
    )

    main_camera_panel.data_updated.connect(on_management_edit_page_data_updated)
    connect_optional_signal(
        main_camera_panel,
        "camera_package_membership_changed",
        on_main_camera_panel_package_membership_changed,
    )

    if hasattr(signal_management_panel, "editor"):
        signal_management_panel.editor.signal_changed.connect(on_signal_property_panel_changed)
    connect_optional_signal(
        signal_management_panel,
        "signal_package_membership_changed",
        on_signal_property_panel_package_membership_changed,
    )

    struct_definition_panel.editor.struct_changed.connect(on_struct_property_panel_struct_changed)
    struct_definition_panel.struct_package_membership_changed.connect(on_struct_property_panel_membership_changed)


def bind_validation_detail_panel(
    *,
    validation_panel: Any,
    validation_detail_panel: Any,
) -> None:
    """绑定验证问题列表与右侧详情面板。"""
    if validation_panel is None:
        return
    validation_panel.issue_selected.connect(validation_detail_panel.set_issue)


