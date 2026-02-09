"""管理模式右侧面板：显式注册表（唯一真源）。

目标：
- 收敛“management section_key → 右侧 tab 显隐/刷新策略”的配置，避免散落 if/elif；
- 让 `RightPanelPolicy` 与 `ManagementPanelsCoordinator` 共享同一份规则，减少隐式依赖；
- 让 `RightPanelAssemblyFeature` 的管理模式 tab 注册矩阵可由同一处配置驱动，降低新增/改名风险。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.models.view_modes import ViewMode


@dataclass(frozen=True, slots=True)
class ManagementRightPanelDynamicTabBlueprint:
    """声明一个“由主窗口属性提供 widget 的动态 tab”。"""

    tab_id: str
    title: str
    main_window_attribute: str
    allowed_modes: tuple[ViewMode, ...]


MANAGEMENT_RIGHT_PANEL_DYNAMIC_TABS: tuple[ManagementRightPanelDynamicTabBlueprint, ...] = (
    ManagementRightPanelDynamicTabBlueprint(
        tab_id="ui_settings",
        title="界面控件设置",
        main_window_attribute="ui_control_settings_panel",
        allowed_modes=(ViewMode.MANAGEMENT,),
    ),
    ManagementRightPanelDynamicTabBlueprint(
        tab_id="signal_editor",
        title="信号",
        main_window_attribute="signal_management_panel",
        allowed_modes=(ViewMode.MANAGEMENT,),
    ),
    ManagementRightPanelDynamicTabBlueprint(
        tab_id="struct_editor",
        title="结构体",
        main_window_attribute="struct_definition_panel",
        allowed_modes=(ViewMode.MANAGEMENT,),
    ),
    ManagementRightPanelDynamicTabBlueprint(
        tab_id="main_camera_editor",
        title="主镜头",
        main_window_attribute="main_camera_panel",
        allowed_modes=(ViewMode.MANAGEMENT,),
    ),
    ManagementRightPanelDynamicTabBlueprint(
        tab_id="peripheral_system_editor",
        title="外围系统",
        main_window_attribute="peripheral_system_panel",
        allowed_modes=(ViewMode.MANAGEMENT,),
    ),
    ManagementRightPanelDynamicTabBlueprint(
        tab_id="equipment_entry_editor",
        title="装备词条",
        main_window_attribute="equipment_entry_panel",
        allowed_modes=(ViewMode.MANAGEMENT,),
    ),
    ManagementRightPanelDynamicTabBlueprint(
        tab_id="equipment_tag_editor",
        title="装备标签",
        main_window_attribute="equipment_tag_panel",
        allowed_modes=(ViewMode.MANAGEMENT,),
    ),
    ManagementRightPanelDynamicTabBlueprint(
        tab_id="equipment_type_editor",
        title="装备类型",
        main_window_attribute="equipment_type_panel",
        allowed_modes=(ViewMode.MANAGEMENT,),
    ),
)


def iter_management_right_panel_tab_ids() -> tuple[str, ...]:
    """管理模式右侧相关动态 tab_id（用于统一 hide/show）。"""

    return tuple(spec.tab_id for spec in MANAGEMENT_RIGHT_PANEL_DYNAMIC_TABS)


def _bind_ui_control_group_manager(main_window: Any) -> None:
    management_widget = getattr(main_window, "management_widget", None)
    if management_widget is None:
        return
    if not hasattr(management_widget, "ui_control_group_manager"):
        return
    ui_panel = getattr(main_window, "ui_control_settings_panel", None)
    if ui_panel is None:
        return
    bind_method = getattr(ui_panel, "bind_manager", None)
    if callable(bind_method):
        bind_method(management_widget.ui_control_group_manager)


ManagementSelection = tuple[str, str] | None
ManagementSectionSelectionUpdater = Callable[[Any, ManagementSelection], None]


def _get_current_package_for_management(main_window: Any) -> object | None:
    package_controller = getattr(main_window, "package_controller", None)
    return getattr(package_controller, "current_package", None)


def update_signal_management_panel_for_selection(
    main_window: Any, selection: ManagementSelection
) -> None:
    """根据当前管理库选中记录刷新信号详情面板（只读展示）。"""
    if selection is None:
        main_window.signal_management_panel.reset()
        return

    section_key, signal_id = selection
    if section_key != "signals" or not signal_id:
        main_window.signal_management_panel.reset()
        return

    package = _get_current_package_for_management(main_window)
    if package is None:
        main_window.signal_management_panel.reset()
        return

    from app.ui.graph.library_pages.management_section_signals import SignalSection

    signals_dict = SignalSection._get_signal_dict_from_package(package)
    if signal_id not in signals_dict:
        main_window.signal_management_panel.reset()
        return

    config = signals_dict[signal_id]
    main_window.signal_management_panel.editor.load_from_config(config)

    display_name = config.signal_name or signal_id
    main_window.signal_management_panel.set_title(f"编辑信号：{display_name}")
    main_window.signal_management_panel.set_description(
        "信号定义当前为代码级只读视图：右侧内容仅供查看与校验，实际修改请在 Python 模块中完成。"
    )

    usage_stats = SignalSection._build_signal_usage_stats(package)
    usage_entry = usage_stats.get(signal_id)
    if usage_entry:
        graph_count = int(usage_entry.get("graph_count", 0))
        node_count = int(usage_entry.get("node_count", 0))
        if graph_count > 0 or node_count > 0:
            usage_text = f"已在 {graph_count} 个图 / {node_count} 个节点中使用"
        else:
            usage_text = "未在任何服务器节点图中使用"
    else:
        usage_text = "未在任何服务器节点图中使用"
    main_window.signal_management_panel.set_usage_text(usage_text)

    packages = main_window.app_state.package_index_manager.list_packages()
    owner_id = main_window.app_state.package_index_manager.get_resource_owner_root_id(
        resource_type="management_signals",
        resource_id=signal_id,
    )
    membership = {owner_id} if owner_id else set()
    main_window.signal_management_panel.set_current_signal_id(signal_id)
    main_window.signal_management_panel.set_signal_membership(packages, membership)


def update_struct_definition_panel_for_selection(
    main_window: Any, selection: ManagementSelection
) -> None:
    """根据当前管理库选中记录刷新结构体详情面板（只读展示）。"""
    if selection is None:
        main_window.struct_definition_panel.reset()
        return

    section_key, struct_id = selection
    if section_key not in ("struct_definitions", "ingame_struct_definitions") or not struct_id:
        main_window.struct_definition_panel.reset()
        return

    package = _get_current_package_for_management(main_window)
    if package is None:
        main_window.struct_definition_panel.reset()
        return

    from engine.configs.specialized.node_graph_configs import (
        STRUCT_TYPE_BASIC,
        STRUCT_TYPE_INGAME_SAVE,
    )
    from engine.resources.resource_manager import ResourceManager
    from app.ui.graph.library_pages.management_section_struct_definitions import (
        StructDefinitionSection,
    )

    resource_manager_candidate = getattr(package, "resource_manager", None)
    if not isinstance(resource_manager_candidate, ResourceManager):
        main_window.struct_definition_panel.reset()
        return

    from engine.configs.specialized.struct_definitions_data import get_struct_payload

    payload = get_struct_payload(struct_id, resource_manager_candidate)
    if not isinstance(payload, dict):
        main_window.struct_definition_panel.reset()
        return

    struct_type_value = (
        STRUCT_TYPE_INGAME_SAVE if section_key == "ingame_struct_definitions" else STRUCT_TYPE_BASIC
    )
    _, initial_fields = StructDefinitionSection._extract_initial_fields_from_struct_data(payload)
    display_name = StructDefinitionSection._get_struct_display_name(struct_id, payload)

    editor_widget = getattr(main_window.struct_definition_panel, "editor", None)
    if editor_widget is None:
        main_window.struct_definition_panel.reset()
        return

    setattr(editor_widget, "_struct_type", struct_type_value)
    editor_widget.load_struct(
        struct_name=display_name,
        fields=initial_fields,
        allow_edit_name=False,
    )
    if hasattr(editor_widget, "set_read_only"):
        editor_widget.set_read_only(True)  # type: ignore[attr-defined]

    main_window._struct_editor_snapshot = editor_widget.build_struct_data()
    main_window._struct_editor_snapshot_id = struct_id

    field_count = StructDefinitionSection._calculate_field_count(payload)
    main_window.struct_definition_panel.set_field_count(field_count)
    main_window.struct_definition_panel.set_title(f"编辑结构体：{display_name}")
    main_window.struct_definition_panel.set_description(
        "结构体定义当前为代码级只读视图：右侧内容仅供查看与校验，实际修改请在 Python 模块中完成。"
    )

    packages = main_window.app_state.package_index_manager.list_packages()
    owner_id = main_window.app_state.package_index_manager.get_resource_owner_root_id(
        resource_type="management_struct_definitions",
        resource_id=struct_id,
    )
    membership = {owner_id} if owner_id else set()
    main_window.struct_definition_panel.set_current_struct_id(struct_id)
    main_window.struct_definition_panel.set_packages_and_membership(packages, membership)


def update_main_camera_panel_for_selection(main_window: Any, selection: ManagementSelection) -> None:
    if selection is None:
        main_window.main_camera_panel.clear()
        return

    section_key, camera_id = selection
    if section_key != "main_cameras" or not camera_id:
        main_window.main_camera_panel.clear()
        return

    package = _get_current_package_for_management(main_window)
    if package is None:
        main_window.main_camera_panel.clear()
        return

    main_window.main_camera_panel.set_context(package, camera_id)


def update_peripheral_system_panel_for_selection(
    main_window: Any, selection: ManagementSelection
) -> None:
    if selection is None:
        main_window.peripheral_system_panel.clear()
        return

    section_key, system_id = selection
    if section_key != "peripheral_systems" or not system_id:
        main_window.peripheral_system_panel.clear()
        return

    package = _get_current_package_for_management(main_window)
    if package is None:
        main_window.peripheral_system_panel.clear()
        return

    main_window.peripheral_system_panel.set_context(package, system_id)

    packages, membership = main_window._get_management_packages_and_membership("peripheral_systems", system_id)
    if hasattr(main_window.peripheral_system_panel, "set_current_system_id"):
        main_window.peripheral_system_panel.set_current_system_id(system_id)  # type: ignore[attr-defined]
    if hasattr(main_window.peripheral_system_panel, "set_packages_and_membership"):
        main_window.peripheral_system_panel.set_packages_and_membership(  # type: ignore[attr-defined]
            packages,
            membership,
        )


def _get_equipment_payload(package: object, storage_id: str) -> dict[str, Any] | None:
    management_view = getattr(package, "management", None)
    equipment_map = getattr(management_view, "equipment_data", None)
    if not isinstance(equipment_map, dict):
        return None
    payload_any = equipment_map.get(storage_id)
    return payload_any if isinstance(payload_any, dict) else None


def update_equipment_entry_panel_for_selection(
    main_window: Any, selection: ManagementSelection
) -> None:
    if selection is None:
        main_window.equipment_entry_panel.clear()
        return

    section_key, storage_id = selection
    if section_key != "equipment_entries" or not storage_id:
        main_window.equipment_entry_panel.clear()
        return

    package = _get_current_package_for_management(main_window)
    if package is None:
        main_window.equipment_entry_panel.clear()
        return

    payload = _get_equipment_payload(package, storage_id)
    if not (isinstance(payload, dict) and (("entry_name" in payload) or ("entry_type" in payload))):
        main_window.equipment_entry_panel.clear()
        return

    main_window.equipment_entry_panel._set_context_internal(package, storage_id, payload)  # type: ignore[attr-defined]
    packages, membership = main_window._get_management_packages_and_membership("equipment_data", storage_id)
    main_window.equipment_entry_panel.set_packages_and_membership(packages, membership)


def update_equipment_tag_panel_for_selection(main_window: Any, selection: ManagementSelection) -> None:
    if selection is None:
        main_window.equipment_tag_panel.clear()
        return

    section_key, storage_id = selection
    if section_key != "equipment_tags" or not storage_id:
        main_window.equipment_tag_panel.clear()
        return

    package = _get_current_package_for_management(main_window)
    if package is None:
        main_window.equipment_tag_panel.clear()
        return

    payload = _get_equipment_payload(package, storage_id)
    if not (isinstance(payload, dict) and ("tag_name" in payload)):
        main_window.equipment_tag_panel.clear()
        return

    main_window.equipment_tag_panel._set_context_internal(package, storage_id, payload)  # type: ignore[attr-defined]
    packages, membership = main_window._get_management_packages_and_membership("equipment_data", storage_id)
    main_window.equipment_tag_panel.set_packages_and_membership(packages, membership)


def update_equipment_type_panel_for_selection(main_window: Any, selection: ManagementSelection) -> None:
    if selection is None:
        main_window.equipment_type_panel.clear()
        return

    section_key, storage_id = selection
    if section_key != "equipment_types" or not storage_id:
        main_window.equipment_type_panel.clear()
        return

    package = _get_current_package_for_management(main_window)
    if package is None:
        main_window.equipment_type_panel.clear()
        return

    payload = _get_equipment_payload(package, storage_id)
    if not (isinstance(payload, dict) and (("type_name" in payload) or ("allowed_slots" in payload))):
        main_window.equipment_type_panel.clear()
        return

    main_window.equipment_type_panel._set_context_internal(package, storage_id, payload)  # type: ignore[attr-defined]
    packages, membership = main_window._get_management_packages_and_membership("equipment_data", storage_id)
    main_window.equipment_type_panel.set_packages_and_membership(packages, membership)


@dataclass(frozen=True, slots=True)
class ManagementSectionRightPanelRule:
    """声明某个管理 section 在右侧的表现规则。"""

    section_keys: tuple[str, ...]
    tab_id: str
    selection_required: bool
    selection_updater: ManagementSectionSelectionUpdater | None = None
    on_section_enter: Callable[[Any], None] | None = None


MANAGEMENT_SECTION_RIGHT_PANEL_RULES: tuple[ManagementSectionRightPanelRule, ...] = (
    ManagementSectionRightPanelRule(
        section_keys=("ui_control_groups",),
        tab_id="ui_settings",
        selection_required=False,
        selection_updater=None,
        on_section_enter=_bind_ui_control_group_manager,
    ),
    ManagementSectionRightPanelRule(
        section_keys=("signals",),
        tab_id="signal_editor",
        selection_required=True,
        selection_updater=update_signal_management_panel_for_selection,
    ),
    ManagementSectionRightPanelRule(
        section_keys=("struct_definitions", "ingame_struct_definitions"),
        tab_id="struct_editor",
        selection_required=True,
        selection_updater=update_struct_definition_panel_for_selection,
    ),
    ManagementSectionRightPanelRule(
        section_keys=("main_cameras",),
        tab_id="main_camera_editor",
        selection_required=True,
        selection_updater=update_main_camera_panel_for_selection,
    ),
    ManagementSectionRightPanelRule(
        section_keys=("peripheral_systems",),
        tab_id="peripheral_system_editor",
        selection_required=True,
        selection_updater=update_peripheral_system_panel_for_selection,
    ),
    ManagementSectionRightPanelRule(
        section_keys=("equipment_entries",),
        tab_id="equipment_entry_editor",
        selection_required=True,
        selection_updater=update_equipment_entry_panel_for_selection,
    ),
    ManagementSectionRightPanelRule(
        section_keys=("equipment_tags",),
        tab_id="equipment_tag_editor",
        selection_required=True,
        selection_updater=update_equipment_tag_panel_for_selection,
    ),
    ManagementSectionRightPanelRule(
        section_keys=("equipment_types",),
        tab_id="equipment_type_editor",
        selection_required=True,
        selection_updater=update_equipment_type_panel_for_selection,
    ),
)


_MANAGEMENT_RULES_BY_SECTION_KEY: dict[str, ManagementSectionRightPanelRule] = {}
for _rule in MANAGEMENT_SECTION_RIGHT_PANEL_RULES:
    for _section_key in _rule.section_keys:
        if _section_key in _MANAGEMENT_RULES_BY_SECTION_KEY:
            raise RuntimeError(f"重复注册的 management section right panel rule: {_section_key!r}")
        _MANAGEMENT_RULES_BY_SECTION_KEY[_section_key] = _rule


def get_management_section_right_panel_rule(
    section_key: str | None,
) -> ManagementSectionRightPanelRule | None:
    if not isinstance(section_key, str) or not section_key:
        return None
    return _MANAGEMENT_RULES_BY_SECTION_KEY.get(section_key)


def iter_management_special_panel_updaters() -> tuple[ManagementSectionSelectionUpdater, ...]:
    """管理模式下“专用编辑面板”的刷新入口集合（去重）。

    用于在空选中或切换 section 时统一 reset 专用面板内容，避免残留旧上下文。
    """
    seen: set[int] = set()
    updaters: list[ManagementSectionSelectionUpdater] = []
    for rule in MANAGEMENT_SECTION_RIGHT_PANEL_RULES:
        updater = rule.selection_updater
        if updater is None:
            continue
        updater_identity = id(updater)
        if updater_identity in seen:
            continue
        seen.add(updater_identity)
        updaters.append(updater)
    return tuple(updaters)


__all__ = [
    "MANAGEMENT_RIGHT_PANEL_DYNAMIC_TABS",
    "MANAGEMENT_SECTION_RIGHT_PANEL_RULES",
    "ManagementRightPanelDynamicTabBlueprint",
    "ManagementSectionRightPanelRule",
    "get_management_section_right_panel_rule",
    "iter_management_special_panel_updaters",
    "iter_management_right_panel_tab_ids",
]


