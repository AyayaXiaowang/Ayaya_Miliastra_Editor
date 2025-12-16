from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.models.view_modes import ViewMode


@dataclass(slots=True)
class _ManagementTabRules:
    ui_settings_section: str = "ui_control_groups"
    signal_section: str = "signals"
    struct_sections: tuple[str, str] = ("struct_definitions", "ingame_struct_definitions")
    main_camera_section: str = "main_cameras"
    peripheral_system_section: str = "peripheral_systems"
    equipment_entry_section: str = "equipment_entries"
    equipment_tag_section: str = "equipment_tags"
    equipment_type_section: str = "equipment_types"


class RightPanelPolicy:
    """右侧标签联动策略：把“section/mode → tabs 显隐”集中到一个地方。"""

    def __init__(self, main_window: Any) -> None:
        self._main_window = main_window
        self._rules = _ManagementTabRules()

    # === 基础能力 ==========================================================

    def set_tab_visible(self, tab_id: str, *, visible: bool, switch_to: bool = False) -> None:
        registry = getattr(self._main_window, "right_panel_registry", None)
        if registry is None:
            raise RuntimeError("RightPanelPolicy 需要 main_window.right_panel_registry 已初始化")
        registry.ensure_visible(tab_id, visible=visible, switch_to=switch_to)

    # === 管理模式：section → tabs ==========================================

    def apply_management_section(self, section_key: str | None) -> None:
        """根据管理面板 section_key 收敛右侧管理相关 tabs。"""
        current_mode = ViewMode.from_index(self._main_window.central_stack.currentIndex())
        if current_mode != ViewMode.MANAGEMENT:
            return

        if section_key is None:
            section_key = self._get_current_management_section_key()

        rules = self._rules
        is_ui_settings = section_key == rules.ui_settings_section
        is_signal = section_key == rules.signal_section
        is_struct = section_key in rules.struct_sections
        is_main_camera = section_key == rules.main_camera_section
        is_peripheral_system = section_key == rules.peripheral_system_section
        is_equipment_entry = section_key == rules.equipment_entry_section
        is_equipment_tag = section_key == rules.equipment_tag_section
        is_equipment_type = section_key == rules.equipment_type_section

        # 先统一隐藏，再按规则开启（避免跨 section 残留）
        self.set_tab_visible("ui_settings", visible=False)
        self.set_tab_visible("signal_editor", visible=False)
        self.set_tab_visible("struct_editor", visible=False)
        self.set_tab_visible("main_camera_editor", visible=False)
        self.set_tab_visible("peripheral_system_editor", visible=False)
        self.set_tab_visible("equipment_entry_editor", visible=False)
        self.set_tab_visible("equipment_tag_editor", visible=False)
        self.set_tab_visible("equipment_type_editor", visible=False)

        if is_ui_settings:
            self._bind_ui_control_group_manager()
            self.set_tab_visible("ui_settings", visible=True)
        if is_signal:
            self.set_tab_visible("signal_editor", visible=True)
        if is_struct:
            self.set_tab_visible("struct_editor", visible=True)
        if is_main_camera:
            self.set_tab_visible("main_camera_editor", visible=True)
        if is_peripheral_system:
            self.set_tab_visible("peripheral_system_editor", visible=True)
        if is_equipment_entry:
            self.set_tab_visible("equipment_entry_editor", visible=True)
        if is_equipment_tag:
            self.set_tab_visible("equipment_tag_editor", visible=True)
        if is_equipment_type:
            self.set_tab_visible("equipment_type_editor", visible=True)

    def _bind_ui_control_group_manager(self) -> None:
        management_widget = getattr(self._main_window, "management_widget", None)
        if management_widget is None:
            return
        if not hasattr(management_widget, "ui_control_group_manager"):
            return
        ui_panel = getattr(self._main_window, "ui_control_settings_panel", None)
        if ui_panel is None:
            return
        bind_method = getattr(ui_panel, "bind_manager", None)
        if callable(bind_method):
            bind_method(management_widget.ui_control_group_manager)

    def _get_current_management_section_key(self) -> str | None:
        management_widget = getattr(self._main_window, "management_widget", None)
        if management_widget is None:
            return None
        getter = getattr(management_widget, "get_current_section_key", None)
        if callable(getter):
            value = getter()
            return value if isinstance(value, str) and value else None
        value = getattr(management_widget, "_last_selected_section_key", None)
        return value if isinstance(value, str) and value else None

    # === 战斗预设：上下文 → tabs ==========================================

    def set_combat_detail_tabs_visible(
        self,
        *,
        player_template: bool = False,
        player_class: bool = False,
        skill: bool = False,
        item: bool = False,
    ) -> None:
        """统一控制战斗预设详情 tabs 的存在性（避免残留空 tab）。"""
        self.set_tab_visible("player_editor", visible=player_template)
        self.set_tab_visible("player_class_editor", visible=player_class)
        self.set_tab_visible("skill_editor", visible=skill)
        self.set_tab_visible("item_editor", visible=item)

    def reset_combat_detail_tabs(self) -> None:
        self.set_combat_detail_tabs_visible(
            player_template=False,
            player_class=False,
            skill=False,
            item=False,
        )


