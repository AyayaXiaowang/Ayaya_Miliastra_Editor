"""
CombatPlayerEditorPanel 拆分模块：角色编辑字段加载与写回（非自定义变量部分）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional


class CombatPlayerPanelSectionsRoleFieldsMixin:
    current_template_data: Optional[Dict[str, Any]]
    player_editor: Any
    role_combat_settings_section: Any

    role_play_own_sound_switch: Any
    role_attributes_edit: Any

    def _load_role_fields(self) -> None:
        role = self.player_editor.role

        self.role_play_own_sound_switch.blockSignals(True)
        self.role_play_own_sound_switch.setChecked(bool(role.get("play_own_sound", False)))
        self.role_play_own_sound_switch.blockSignals(False)

        self.role_attributes_edit.blockSignals(True)
        self.role_attributes_edit.setPlainText(str(role.get("attributes_text", "")).strip())
        self.role_attributes_edit.blockSignals(False)

        combat_settings_data = role.get("combat_settings")
        if self.role_combat_settings_section is not None:
            self.role_combat_settings_section.set_from_metadata(combat_settings_data)

        # 加载角色层级自定义变量
        self._load_role_custom_variables()

    # --- 角色字段写回 ---------------------------------------------------------

    def _on_role_play_own_sound_changed(self, checked: bool) -> None:
        if not self.current_template_data:
            return
        role = self.player_editor.role
        role["play_own_sound"] = bool(checked)
        role["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_role_attributes_changed(self) -> None:
        if not self.current_template_data:
            return
        role = self.player_editor.role
        role["attributes_text"] = self.role_attributes_edit.toPlainText()
        role["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_role_combat_settings_changed(self) -> None:
        if not self.current_template_data or self.role_combat_settings_section is None:
            return
        role = self.player_editor.role
        combat_settings_data = self.role_combat_settings_section.to_metadata()
        role["combat_settings"] = combat_settings_data
        role["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._mark_template_modified()
        self.data_changed.emit()


