"""
CombatPlayerEditorPanel 拆分模块：玩家编辑字段加载与写回。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6 import QtCore


class CombatPlayerPanelSectionsPlayerFieldsMixin:
    current_template_data: Optional[Dict[str, Any]]
    player_editor: Any

    all_players_checkbox: Any
    player_selection_checkboxes: List[Any]

    level_spin: Any
    spawn_point_combo: Any
    profession_combo: Any

    allow_resurrection_check: Any
    show_resurrection_ui_check: Any
    resurrection_time_spin: Any
    auto_resurrection_check: Any
    resurrection_count_limit_check: Any
    resurrection_count_spin: Any
    resurrection_points_edit: Any
    resurrection_point_rule_combo: Any
    resurrection_health_ratio_spin: Any
    special_knockout_pct_spin: Any

    def _load_player_fields(self) -> None:
        if not self.current_template_data:
            self._clear_ui()
            return

        template = self.current_template_data
        player_section = self.player_editor.player

        # 加载生效目标
        selected_players = player_section.get("selected_players", [])
        all_players_selected = player_section.get("all_players", False)

        self.all_players_checkbox.blockSignals(True)
        self.all_players_checkbox.setChecked(all_players_selected)
        self.all_players_checkbox.blockSignals(False)

        for checkbox in self.player_selection_checkboxes:
            player_index = checkbox.property("player_index")
            checkbox.blockSignals(True)
            checkbox.setChecked(player_index in selected_players)
            checkbox.blockSignals(False)

        # 加载基础属性
        self.level_spin.blockSignals(True)
        self.level_spin.setValue(int(template.get("level", 1)))
        self.level_spin.blockSignals(False)

        spawn_point = str(player_section.get("spawn_point", "")).strip()
        self.spawn_point_combo.blockSignals(True)
        self.spawn_point_combo.setCurrentText(spawn_point)
        self.spawn_point_combo.blockSignals(False)

        profession_id = str(template.get("default_profession_id", "")).strip()
        self.profession_combo.blockSignals(True)
        self.profession_combo.setCurrentText(profession_id)
        self.profession_combo.blockSignals(False)

        # 加载复苏属性（schema 绑定表单）
        if hasattr(self, "_player_resurrection_schema_form"):
            self._player_resurrection_schema_form.set_model(self.player_editor.player)
            self._player_resurrection_schema_form.load_from_model()

        # 加载特殊被击倒损伤
        self.special_knockout_pct_spin.blockSignals(True)
        self.special_knockout_pct_spin.setValue(
            float(player_section.get("special_knockout_pct", 0.0))
        )
        self.special_knockout_pct_spin.blockSignals(False)

        # 加载玩家层级自定义变量（不包含局内存档 chip 变量）
        self._load_player_custom_variables()

        # 加载局内存档模板绑定与 chip 变量视图
        self._load_player_ingame_save_binding()

    def _on_all_players_changed(self, state: int) -> None:
        if not self.current_template_data:
            return
        is_checked = state == QtCore.Qt.CheckState.Checked.value
        self.player_editor.player["all_players"] = is_checked

        # 如果选中全部玩家，则取消其他选项
        if is_checked:
            for checkbox in self.player_selection_checkboxes:
                checkbox.blockSignals(True)
                checkbox.setChecked(False)
                checkbox.blockSignals(False)
            self.player_editor.player["selected_players"] = []

        self._mark_template_modified()
        self.data_changed.emit()

    def _on_player_selection_changed(self, state: int) -> None:  # noqa: ARG002
        if not self.current_template_data:
            return

        selected_players: List[int] = []
        for checkbox in self.player_selection_checkboxes:
            if checkbox.isChecked():
                player_index = checkbox.property("player_index")
                selected_players.append(player_index)

        # 如果选择了具体玩家，则取消"全部玩家"选项
        if selected_players:
            self.all_players_checkbox.blockSignals(True)
            self.all_players_checkbox.setChecked(False)
            self.all_players_checkbox.blockSignals(False)
            self.player_editor.player["all_players"] = False

        self.player_editor.player["selected_players"] = selected_players
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_level_changed(self, value: int) -> None:
        if not self.current_template_data:
            return
        self.current_template_data["level"] = int(value)
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_spawn_point_changed(self, text: str) -> None:
        if not self.current_template_data:
            return
        self.player_editor.player["spawn_point"] = text.strip()
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_profession_changed(self, text: str) -> None:
        if not self.current_template_data:
            return
        self.current_template_data["default_profession_id"] = text.strip()
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_allow_resurrection_changed(self, state: int) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["allow_resurrection"] = state == QtCore.Qt.CheckState.Checked.value
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_show_resurrection_ui_changed(self, state: int) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["show_ui"] = state == QtCore.Qt.CheckState.Checked.value
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_resurrection_time_changed(self, value: float) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["time"] = float(value)
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_auto_resurrection_changed(self, state: int) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["auto_resurrection"] = state == QtCore.Qt.CheckState.Checked.value
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_resurrection_count_limit_changed(self, state: int) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["count_limit"] = state == QtCore.Qt.CheckState.Checked.value
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_resurrection_count_changed(self, value: int) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["count"] = int(value)
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_resurrection_points_changed(self) -> None:
        if not self.current_template_data:
            return
        text = self.resurrection_points_edit.toPlainText()
        points = [line.strip() for line in text.split("\n") if line.strip()]
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["points"] = points
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_resurrection_point_rule_changed(self, index: int) -> None:
        if not self.current_template_data:
            return
        rule_mapping = {
            0: "nearest",
            1: "latest_activated",
            2: "highest_priority",
            3: "random",
        }
        rule = rule_mapping.get(index, "nearest")
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["point_rule"] = rule
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_resurrection_health_ratio_changed(self, value: float) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["health_ratio"] = float(value)
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_special_knockout_changed(self, value: float) -> None:
        if not self.current_template_data:
            return
        self.player_editor.player["special_knockout_pct"] = float(value)
        self._mark_template_modified()
        self.data_changed.emit()


