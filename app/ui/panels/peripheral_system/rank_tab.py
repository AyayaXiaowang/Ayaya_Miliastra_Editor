from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.toggle_switch import ToggleSwitch


class PeripheralRankTab(QtWidgets.QWidget):
    """外围系统：竞技段位 Tab（就地编辑 system_payload['competitive_rank_settings']）。"""

    data_updated = QtCore.pyqtSignal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._system_payload: Optional[Dict[str, Any]] = None

        self._build_ui()
        self._bind_signals()
        self.setEnabled(False)

    # ------------------------------ Public

    def set_system_payload(self, system_payload: Optional[Dict[str, Any]]) -> None:
        self._system_payload = system_payload
        if self._system_payload is None:
            self.clear()
            return
        self._load_tab()
        self.setEnabled(True)

    def clear(self) -> None:
        self._system_payload = None
        self._set_rank_enabled(False, False)
        self.rank_announcement_edit.blockSignals(True)
        self.rank_announcement_edit.setPlainText("")
        self.rank_announcement_edit.blockSignals(False)
        self.rank_group_list.clear()
        self._clear_rank_group_form()
        self.setEnabled(False)

    # ------------------------------ UI build

    def _build_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(Sizes.SPACING_MEDIUM)

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        main_layout.addWidget(scroll_area)

        container = QtWidgets.QWidget(scroll_area)
        scroll_layout = QtWidgets.QVBoxLayout(container)
        scroll_layout.setContentsMargins(
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
        )
        scroll_layout.setSpacing(Sizes.SPACING_MEDIUM)

        settings_group = QtWidgets.QGroupBox("竞技段位设置")
        settings_layout = QtWidgets.QFormLayout(settings_group)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setHorizontalSpacing(Sizes.SPACING_SMALL)
        settings_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        self.rank_enabled_switch = ToggleSwitch()
        self.rank_allow_room_switch = ToggleSwitch()
        self.rank_announcement_edit = QtWidgets.QTextEdit()
        self.rank_announcement_edit.setMinimumHeight(80)
        self.rank_announcement_edit.setMaximumHeight(180)

        settings_layout.addRow("是否开启竞技段位:", self.rank_enabled_switch)
        settings_layout.addRow("允许房间内游玩结算分数:", self.rank_allow_room_switch)
        settings_layout.addRow("奇匠留言:", self.rank_announcement_edit)
        scroll_layout.addWidget(settings_group)

        group_box = QtWidgets.QGroupBox("计分组设置")
        group_box.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )
        group_layout = QtWidgets.QVBoxLayout(group_box)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(Sizes.SPACING_SMALL)

        self.rank_group_list = QtWidgets.QListWidget()
        self.rank_group_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.rank_group_list.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        group_layout.addWidget(self.rank_group_list)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setHorizontalSpacing(Sizes.SPACING_SMALL)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        self.rank_group_name_edit = QtWidgets.QLineEdit()
        self.rank_group_index_spin = QtWidgets.QSpinBox()
        self.rank_group_index_spin.setRange(1, 9999)
        self.rank_victory_score_spin = QtWidgets.QSpinBox()
        self.rank_victory_score_spin.setRange(-9999, 9999)
        self.rank_defeat_score_spin = QtWidgets.QSpinBox()
        self.rank_defeat_score_spin.setRange(-9999, 9999)
        self.rank_unsettled_score_spin = QtWidgets.QSpinBox()
        self.rank_unsettled_score_spin.setRange(-9999, 9999)
        self.rank_escape_score_spin = QtWidgets.QSpinBox()
        self.rank_escape_score_spin.setRange(-9999, 9999)

        self.rank_applied_players_combo = QtWidgets.QComboBox()
        self.rank_applied_players_combo.addItems(["所有人", "仅房主", "仅队长"])

        form_layout.addRow("计分组名称:", self.rank_group_name_edit)
        form_layout.addRow("序号:", self.rank_group_index_spin)
        form_layout.addRow("胜利分数:", self.rank_victory_score_spin)
        form_layout.addRow("失败分数:", self.rank_defeat_score_spin)
        form_layout.addRow("未定分数:", self.rank_unsettled_score_spin)
        form_layout.addRow("逃跑分数:", self.rank_escape_score_spin)
        form_layout.addRow("包含的玩家:", self.rank_applied_players_combo)

        group_layout.addLayout(form_layout)
        scroll_layout.addWidget(group_box)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        self.add_rank_group_button = QtWidgets.QPushButton("新建计分组")
        self.remove_rank_group_button = QtWidgets.QPushButton("删除选中")
        button_row.addWidget(self.add_rank_group_button)
        button_row.addWidget(self.remove_rank_group_button)
        scroll_layout.addLayout(button_row)

        scroll_layout.addStretch(1)
        scroll_area.setWidget(container)

    def _bind_signals(self) -> None:
        self.rank_enabled_switch.stateChanged.connect(self._on_rank_enabled_changed)
        self.rank_allow_room_switch.stateChanged.connect(
            self._on_rank_allow_room_changed
        )
        self.rank_announcement_edit.textChanged.connect(self._on_rank_announcement_changed)

        self.rank_group_list.customContextMenuRequested.connect(
            self._on_rank_group_context_menu
        )
        self.rank_group_list.currentRowChanged.connect(self._on_rank_group_row_changed)

        self.rank_group_name_edit.editingFinished.connect(self._apply_rank_group_form_changes)
        self.rank_group_index_spin.valueChanged.connect(self._apply_rank_group_form_changes)
        self.rank_victory_score_spin.valueChanged.connect(self._apply_rank_group_form_changes)
        self.rank_defeat_score_spin.valueChanged.connect(self._apply_rank_group_form_changes)
        self.rank_unsettled_score_spin.valueChanged.connect(self._apply_rank_group_form_changes)
        self.rank_escape_score_spin.valueChanged.connect(self._apply_rank_group_form_changes)
        self.rank_applied_players_combo.currentIndexChanged.connect(
            self._apply_rank_group_form_changes
        )

        self.add_rank_group_button.clicked.connect(self._on_add_rank_group_clicked)
        self.remove_rank_group_button.clicked.connect(self._on_remove_rank_group_clicked)

    # ------------------------------ Data helpers

    def _get_rank_settings(self) -> Dict[str, Any]:
        if self._system_payload is None:
            return {}
        settings_any = self._system_payload.get("competitive_rank_settings")
        if not isinstance(settings_any, dict):
            settings_any = {
                "enabled": False,
                "allow_room_settle": False,
                "note": "",
                "score_groups": [],
            }
            self._system_payload["competitive_rank_settings"] = settings_any
        return settings_any

    def _load_tab(self) -> None:
        settings = self._get_rank_settings()
        enabled_flag = bool(settings.get("enabled", False))
        allow_room_flag = bool(settings.get("allow_room_settle", False))
        note_text = str(settings.get("note", "")).strip()

        self._set_rank_enabled(enabled_flag, allow_room_flag)
        self.rank_announcement_edit.blockSignals(True)
        self.rank_announcement_edit.setPlainText(note_text)
        self.rank_announcement_edit.blockSignals(False)

        self.rank_group_list.blockSignals(True)
        self.rank_group_list.clear()
        groups_any = settings.get("score_groups", [])
        groups: List[Dict[str, Any]] = [
            entry for entry in groups_any if isinstance(entry, dict)
        ]
        for group in groups:
            raw_name = group.get("group_name") or group.get("name") or group.get(
                "group_index", ""
            )
            display_name = str(raw_name) if raw_name is not None else ""
            if not display_name:
                display_name = "默认计分组"
            self.rank_group_list.addItem(display_name)
        self.rank_group_list.blockSignals(False)

        if self.rank_group_list.count() > 0:
            self.rank_group_list.setCurrentRow(0)
            self._load_rank_group_form_for_row(0)
        else:
            self._clear_rank_group_form()

    def _set_rank_enabled(self, enabled: bool, allow_room: bool) -> None:
        self.rank_enabled_switch.blockSignals(True)
        self.rank_allow_room_switch.blockSignals(True)
        self.rank_enabled_switch.setChecked(enabled)
        self.rank_allow_room_switch.setChecked(allow_room)
        self.rank_enabled_switch.blockSignals(False)
        self.rank_allow_room_switch.blockSignals(False)

    def _clear_rank_group_form(self) -> None:
        self.rank_group_name_edit.blockSignals(True)
        self.rank_group_index_spin.blockSignals(True)
        self.rank_victory_score_spin.blockSignals(True)
        self.rank_defeat_score_spin.blockSignals(True)
        self.rank_unsettled_score_spin.blockSignals(True)
        self.rank_escape_score_spin.blockSignals(True)
        self.rank_applied_players_combo.blockSignals(True)

        self.rank_group_name_edit.clear()
        self.rank_group_index_spin.setValue(1)
        self.rank_victory_score_spin.setValue(20)
        self.rank_defeat_score_spin.setValue(-5)
        self.rank_unsettled_score_spin.setValue(0)
        self.rank_escape_score_spin.setValue(-20)
        self.rank_applied_players_combo.setCurrentIndex(0)

        self.rank_group_name_edit.blockSignals(False)
        self.rank_group_index_spin.blockSignals(False)
        self.rank_victory_score_spin.blockSignals(False)
        self.rank_defeat_score_spin.blockSignals(False)
        self.rank_unsettled_score_spin.blockSignals(False)
        self.rank_escape_score_spin.blockSignals(False)
        self.rank_applied_players_combo.blockSignals(False)

    def _load_rank_group_form_for_row(self, row_index: int) -> None:
        settings = self._get_rank_settings()
        groups_any = settings.get("score_groups", [])
        if not isinstance(groups_any, list) or row_index < 0 or row_index >= len(groups_any):
            self._clear_rank_group_form()
            return
        group_any = groups_any[row_index]
        if not isinstance(group_any, dict):
            self._clear_rank_group_form()
            return
        group: Dict[str, Any] = group_any

        name_text = str(group.get("group_name", "")).strip()
        index_value = int(group.get("group_index", row_index + 1))
        victory_score = int(group.get("victory_score", 20))
        defeat_score = int(group.get("defeat_score", -5))
        unsettled_score = int(group.get("unsettled_score", 0))
        escape_score = int(group.get("escape_score", -20))
        applied_players = str(group.get("applied_players", "所有人"))

        self.rank_group_name_edit.blockSignals(True)
        self.rank_group_index_spin.blockSignals(True)
        self.rank_victory_score_spin.blockSignals(True)
        self.rank_defeat_score_spin.blockSignals(True)
        self.rank_unsettled_score_spin.blockSignals(True)
        self.rank_escape_score_spin.blockSignals(True)
        self.rank_applied_players_combo.blockSignals(True)

        self.rank_group_name_edit.setText(name_text)
        self.rank_group_index_spin.setValue(index_value)
        self.rank_victory_score_spin.setValue(victory_score)
        self.rank_defeat_score_spin.setValue(defeat_score)
        self.rank_unsettled_score_spin.setValue(unsettled_score)
        self.rank_escape_score_spin.setValue(escape_score)

        index = self.rank_applied_players_combo.findText(applied_players)
        if index < 0:
            index = 0
        self.rank_applied_players_combo.setCurrentIndex(index)

        self.rank_group_name_edit.blockSignals(False)
        self.rank_group_index_spin.blockSignals(False)
        self.rank_victory_score_spin.blockSignals(False)
        self.rank_defeat_score_spin.blockSignals(False)
        self.rank_unsettled_score_spin.blockSignals(False)
        self.rank_escape_score_spin.blockSignals(False)
        self.rank_applied_players_combo.blockSignals(False)

    # ------------------------------ Event handlers

    def _on_rank_enabled_changed(self, state: int) -> None:
        if self._system_payload is None:
            return
        enabled_flag = state == QtCore.Qt.CheckState.Checked.value
        settings = self._get_rank_settings()
        settings["enabled"] = bool(enabled_flag)
        self.data_updated.emit()

    def _on_rank_allow_room_changed(self, state: int) -> None:
        if self._system_payload is None:
            return
        allow_flag = state == QtCore.Qt.CheckState.Checked.value
        settings = self._get_rank_settings()
        settings["allow_room_settle"] = bool(allow_flag)
        self.data_updated.emit()

    def _on_rank_announcement_changed(self) -> None:
        if self._system_payload is None:
            return
        settings = self._get_rank_settings()
        settings["note"] = self.rank_announcement_edit.toPlainText().strip()
        self.data_updated.emit()

    def _on_rank_group_row_changed(self, row_index: int) -> None:
        self._load_rank_group_form_for_row(row_index)

    def _apply_rank_group_form_changes(self) -> None:
        if self._system_payload is None:
            return
        current_row = self.rank_group_list.currentRow()
        if current_row < 0:
            return
        settings = self._get_rank_settings()
        groups_any = settings.get("score_groups", [])
        if not isinstance(groups_any, list) or current_row >= len(groups_any):
            return
        group_any = groups_any[current_row]
        if not isinstance(group_any, dict):
            return
        group: Dict[str, Any] = group_any

        name_text = self.rank_group_name_edit.text().strip()
        index_value = int(self.rank_group_index_spin.value())
        victory_score = int(self.rank_victory_score_spin.value())
        defeat_score = int(self.rank_defeat_score_spin.value())
        unsettled_score = int(self.rank_unsettled_score_spin.value())
        escape_score = int(self.rank_escape_score_spin.value())
        applied_players_text = str(self.rank_applied_players_combo.currentText())

        if name_text:
            group["group_name"] = name_text
        group["group_index"] = index_value
        group["victory_score"] = victory_score
        group["defeat_score"] = defeat_score
        group["unsettled_score"] = unsettled_score
        group["escape_score"] = escape_score
        group["applied_players"] = applied_players_text

        list_item = self.rank_group_list.item(current_row)
        if list_item is not None:
            list_item.setText(name_text or "默认计分组")

        self.data_updated.emit()

    def _remove_rank_group_at_row(self, row_index: int) -> None:
        if self._system_payload is None:
            return
        if row_index < 0:
            return
        settings = self._get_rank_settings()
        groups_any = settings.get("score_groups")
        if not isinstance(groups_any, list):
            return
        if row_index >= len(groups_any):
            return
        del groups_any[row_index]
        self.data_updated.emit()
        self._load_tab()
        if self.rank_group_list.count() > 0:
            next_row = min(row_index, self.rank_group_list.count() - 1)
            self.rank_group_list.setCurrentRow(next_row)

    def _on_remove_rank_group_clicked(self) -> None:
        current_row = self.rank_group_list.currentRow()
        self._remove_rank_group_at_row(current_row)

    def _on_rank_group_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.rank_group_list.itemAt(pos)
        if item is None:
            return
        row_index = self.rank_group_list.row(item)

        def delete_current_row() -> None:
            self._remove_rank_group_at_row(row_index)

        builder = ContextMenuBuilder(self.rank_group_list)
        builder.add_action("删除当前行", delete_current_row)
        builder.exec_for(self.rank_group_list, pos)

    def _on_add_rank_group_clicked(self) -> None:
        if self._system_payload is None:
            return
        settings = self._get_rank_settings()
        groups_any = settings.get("score_groups")
        if not isinstance(groups_any, list):
            groups_any = []
            settings["score_groups"] = groups_any
        groups: List[Any] = groups_any

        existing_ids: List[str] = []
        for group in groups:
            if isinstance(group, dict):
                raw_id = group.get("group_id")
                if isinstance(raw_id, str) and raw_id:
                    existing_ids.append(raw_id)

        new_id = generate_prefixed_id("rank_group")
        while new_id in existing_ids:
            new_id = generate_prefixed_id("rank_group")

        new_index = len(groups) + 1
        new_group: Dict[str, Any] = {
            "group_id": new_id,
            "group_name": f"默认计分组{new_index}",
            "group_index": new_index,
            "victory_score": 20,
            "defeat_score": -5,
            "unsettled_score": 0,
            "escape_score": -20,
            "applied_players": "所有人",
        }
        groups.append(new_group)
        self.data_updated.emit()

        self._load_tab()
        if self.rank_group_list.count() > 0:
            self.rank_group_list.setCurrentRow(self.rank_group_list.count() - 1)


__all__ = ["PeripheralRankTab"]


