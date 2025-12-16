from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.toggle_switch import ToggleSwitch


class PeripheralLeaderboardTab(QtWidgets.QWidget):
    """外围系统：排行榜 Tab（就地编辑 system_payload['leaderboard_settings']）。"""

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
        self._set_leaderboard_enabled(False, False)
        self.leaderboard_list.clear()
        self._clear_leaderboard_form()
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

        settings_group = QtWidgets.QGroupBox("排行榜设置")
        settings_layout = QtWidgets.QFormLayout(settings_group)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setHorizontalSpacing(Sizes.SPACING_SMALL)
        settings_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        self.leaderboard_enabled_switch = ToggleSwitch()
        self.leaderboard_allow_room_switch = ToggleSwitch()
        settings_layout.addRow("是否开启排行榜:", self.leaderboard_enabled_switch)
        settings_layout.addRow("允许房间内游玩结算排行榜:", self.leaderboard_allow_room_switch)
        scroll_layout.addWidget(settings_group)

        list_group = QtWidgets.QGroupBox("排行榜列表")
        list_group.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )
        list_layout = QtWidgets.QVBoxLayout(list_group)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(Sizes.SPACING_SMALL)

        self.leaderboard_list = QtWidgets.QListWidget()
        self.leaderboard_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        list_layout.addWidget(self.leaderboard_list)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setHorizontalSpacing(Sizes.SPACING_SMALL)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        self.leaderboard_name_edit = QtWidgets.QLineEdit()
        self.leaderboard_index_spin = QtWidgets.QSpinBox()
        self.leaderboard_index_spin.setRange(1, 9999)
        self.leaderboard_display_priority_spin = QtWidgets.QSpinBox()
        self.leaderboard_display_priority_spin.setRange(0, 9999)

        self.leaderboard_display_format_combo = QtWidgets.QComboBox()
        self.leaderboard_display_format_combo.addItems(["纯数值", "时间", "百分比"])

        self.leaderboard_reset_type_combo = QtWidgets.QComboBox()
        self.leaderboard_reset_type_combo.addItems(["不重置", "随赛季重置"])

        self.leaderboard_sort_rule_combo = QtWidgets.QComboBox()
        self.leaderboard_sort_rule_combo.addItems(["越大越靠前", "越小越靠前"])

        form_layout.addRow("排行榜名称:", self.leaderboard_name_edit)
        form_layout.addRow("序号:", self.leaderboard_index_spin)
        form_layout.addRow("显示优先级:", self.leaderboard_display_priority_spin)
        form_layout.addRow("显示格式选择:", self.leaderboard_display_format_combo)
        form_layout.addRow("榜单重置类型:", self.leaderboard_reset_type_combo)
        form_layout.addRow("成绩排序规则:", self.leaderboard_sort_rule_combo)

        list_layout.addLayout(form_layout)
        scroll_layout.addWidget(list_group)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        self.add_leaderboard_button = QtWidgets.QPushButton("新建排行榜")
        self.remove_leaderboard_button = QtWidgets.QPushButton("删除选中")
        button_row.addWidget(self.add_leaderboard_button)
        button_row.addWidget(self.remove_leaderboard_button)
        scroll_layout.addLayout(button_row)

        scroll_layout.addStretch(1)
        scroll_area.setWidget(container)

    def _bind_signals(self) -> None:
        self.leaderboard_enabled_switch.stateChanged.connect(
            self._on_leaderboard_enabled_changed
        )
        self.leaderboard_allow_room_switch.stateChanged.connect(
            self._on_leaderboard_allow_room_changed
        )

        self.leaderboard_list.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.leaderboard_list.customContextMenuRequested.connect(
            self._on_leaderboard_context_menu
        )
        self.leaderboard_list.currentRowChanged.connect(self._on_leaderboard_row_changed)

        self.leaderboard_name_edit.editingFinished.connect(
            self._apply_leaderboard_form_changes
        )
        self.leaderboard_index_spin.valueChanged.connect(
            self._apply_leaderboard_form_changes
        )
        self.leaderboard_display_priority_spin.valueChanged.connect(
            self._apply_leaderboard_form_changes
        )
        self.leaderboard_display_format_combo.currentIndexChanged.connect(
            self._apply_leaderboard_form_changes
        )
        self.leaderboard_reset_type_combo.currentIndexChanged.connect(
            self._apply_leaderboard_form_changes
        )
        self.leaderboard_sort_rule_combo.currentIndexChanged.connect(
            self._apply_leaderboard_form_changes
        )

        self.add_leaderboard_button.clicked.connect(self._on_add_leaderboard_clicked)
        self.remove_leaderboard_button.clicked.connect(
            self._on_remove_leaderboard_clicked
        )

    # ------------------------------ Data helpers

    def _get_leaderboard_settings(self) -> Dict[str, Any]:
        if self._system_payload is None:
            return {}
        settings_any = self._system_payload.get("leaderboard_settings")
        if not isinstance(settings_any, dict):
            settings_any = {
                "enabled": False,
                "allow_room_settle": False,
                "records": [],
            }
            self._system_payload["leaderboard_settings"] = settings_any
        return settings_any

    def _load_tab(self) -> None:
        settings = self._get_leaderboard_settings()
        enabled_flag = bool(settings.get("enabled", False))
        allow_room_flag = bool(settings.get("allow_room_settle", False))
        self._set_leaderboard_enabled(enabled_flag, allow_room_flag)

        self.leaderboard_list.blockSignals(True)
        self.leaderboard_list.clear()
        records_any = settings.get("records", [])
        records: List[Dict[str, Any]] = [
            entry for entry in records_any if isinstance(entry, dict)
        ]
        for record in records:
            raw_name = (
                record.get("leaderboard_name")
                or record.get("name")
                or record.get("leaderboard_id", "")
            )
            display_name = str(raw_name) if raw_name is not None else ""
            if not display_name:
                display_name = "未命名排行榜"
            self.leaderboard_list.addItem(display_name)
        self.leaderboard_list.blockSignals(False)

        if self.leaderboard_list.count() > 0:
            self.leaderboard_list.setCurrentRow(0)
            self._load_leaderboard_form_for_row(0)
        else:
            self._clear_leaderboard_form()

    def _set_leaderboard_enabled(self, enabled: bool, allow_room: bool) -> None:
        self.leaderboard_enabled_switch.blockSignals(True)
        self.leaderboard_allow_room_switch.blockSignals(True)
        self.leaderboard_enabled_switch.setChecked(enabled)
        self.leaderboard_allow_room_switch.setChecked(allow_room)
        self.leaderboard_enabled_switch.blockSignals(False)
        self.leaderboard_allow_room_switch.blockSignals(False)

    def _clear_leaderboard_form(self) -> None:
        self.leaderboard_name_edit.blockSignals(True)
        self.leaderboard_index_spin.blockSignals(True)
        self.leaderboard_display_priority_spin.blockSignals(True)
        self.leaderboard_display_format_combo.blockSignals(True)
        self.leaderboard_reset_type_combo.blockSignals(True)
        self.leaderboard_sort_rule_combo.blockSignals(True)

        self.leaderboard_name_edit.clear()
        self.leaderboard_index_spin.setValue(1)
        self.leaderboard_display_priority_spin.setValue(1)
        self.leaderboard_display_format_combo.setCurrentIndex(0)
        self.leaderboard_reset_type_combo.setCurrentIndex(0)
        self.leaderboard_sort_rule_combo.setCurrentIndex(0)

        self.leaderboard_name_edit.blockSignals(False)
        self.leaderboard_index_spin.blockSignals(False)
        self.leaderboard_display_priority_spin.blockSignals(False)
        self.leaderboard_display_format_combo.blockSignals(False)
        self.leaderboard_reset_type_combo.blockSignals(False)
        self.leaderboard_sort_rule_combo.blockSignals(False)

    def _load_leaderboard_form_for_row(self, row_index: int) -> None:
        settings = self._get_leaderboard_settings()
        records_any = settings.get("records", [])
        if (
            not isinstance(records_any, list)
            or row_index < 0
            or row_index >= len(records_any)
        ):
            self._clear_leaderboard_form()
            return
        record_any = records_any[row_index]
        if not isinstance(record_any, dict):
            self._clear_leaderboard_form()
            return
        record: Dict[str, Any] = record_any

        name_text = str(record.get("leaderboard_name", "")).strip()
        order_index = int(record.get("order_index", row_index + 1))
        priority_value = int(record.get("display_priority", 1))
        display_format_value = str(record.get("display_format", "纯数值"))
        reset_type_value = str(record.get("reset_type", "不重置"))
        sort_rule_value = str(record.get("score_sort_rule", "越大越靠前"))

        self.leaderboard_name_edit.blockSignals(True)
        self.leaderboard_index_spin.blockSignals(True)
        self.leaderboard_display_priority_spin.blockSignals(True)
        self.leaderboard_display_format_combo.blockSignals(True)
        self.leaderboard_reset_type_combo.blockSignals(True)
        self.leaderboard_sort_rule_combo.blockSignals(True)

        self.leaderboard_name_edit.setText(name_text)
        self.leaderboard_index_spin.setValue(order_index)
        self.leaderboard_display_priority_spin.setValue(priority_value)

        self._set_combo_by_text(self.leaderboard_display_format_combo, display_format_value)
        self._set_combo_by_text(self.leaderboard_reset_type_combo, reset_type_value)
        self._set_combo_by_text(self.leaderboard_sort_rule_combo, sort_rule_value)

        self.leaderboard_name_edit.blockSignals(False)
        self.leaderboard_index_spin.blockSignals(False)
        self.leaderboard_display_priority_spin.blockSignals(False)
        self.leaderboard_display_format_combo.blockSignals(False)
        self.leaderboard_reset_type_combo.blockSignals(False)
        self.leaderboard_sort_rule_combo.blockSignals(False)

    @staticmethod
    def _set_combo_by_text(combo: QtWidgets.QComboBox, text: str) -> None:
        index = combo.findText(text)
        if index < 0:
            index = 0
        combo.setCurrentIndex(index)

    # ------------------------------ Event handlers

    def _on_leaderboard_enabled_changed(self, state: int) -> None:
        if self._system_payload is None:
            return
        enabled_flag = state == QtCore.Qt.CheckState.Checked.value
        settings = self._get_leaderboard_settings()
        settings["enabled"] = bool(enabled_flag)
        self.data_updated.emit()

    def _on_leaderboard_allow_room_changed(self, state: int) -> None:
        if self._system_payload is None:
            return
        allow_flag = state == QtCore.Qt.CheckState.Checked.value
        settings = self._get_leaderboard_settings()
        settings["allow_room_settle"] = bool(allow_flag)
        self.data_updated.emit()

    def _on_leaderboard_row_changed(self, row_index: int) -> None:
        self._load_leaderboard_form_for_row(row_index)

    def _apply_leaderboard_form_changes(self) -> None:
        if self._system_payload is None:
            return
        current_row = self.leaderboard_list.currentRow()
        if current_row < 0:
            return
        settings = self._get_leaderboard_settings()
        records_any = settings.get("records", [])
        if not isinstance(records_any, list) or current_row >= len(records_any):
            return
        record_any = records_any[current_row]
        if not isinstance(record_any, dict):
            return
        record: Dict[str, Any] = record_any

        name_text = self.leaderboard_name_edit.text().strip()
        order_index_value = int(self.leaderboard_index_spin.value())
        priority_value = int(self.leaderboard_display_priority_spin.value())
        display_format_text = str(self.leaderboard_display_format_combo.currentText())
        reset_type_text = str(self.leaderboard_reset_type_combo.currentText())
        sort_rule_text = str(self.leaderboard_sort_rule_combo.currentText())

        if name_text:
            record["leaderboard_name"] = name_text
        record["order_index"] = order_index_value
        record["display_priority"] = priority_value
        record["display_format"] = display_format_text
        record["reset_type"] = reset_type_text
        record["score_sort_rule"] = sort_rule_text

        list_item = self.leaderboard_list.item(current_row)
        if list_item is not None:
            list_item.setText(name_text or "未命名排行榜")

        self.data_updated.emit()

    def _remove_leaderboard_at_row(self, row_index: int) -> None:
        if self._system_payload is None:
            return
        if row_index < 0:
            return
        settings = self._get_leaderboard_settings()
        records_any = settings.get("records")
        if not isinstance(records_any, list):
            return
        if row_index >= len(records_any):
            return
        del records_any[row_index]
        self.data_updated.emit()
        self._load_tab()
        if self.leaderboard_list.count() > 0:
            next_row = min(row_index, self.leaderboard_list.count() - 1)
            self.leaderboard_list.setCurrentRow(next_row)

    def _on_remove_leaderboard_clicked(self) -> None:
        current_row = self.leaderboard_list.currentRow()
        self._remove_leaderboard_at_row(current_row)

    def _on_leaderboard_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.leaderboard_list.itemAt(pos)
        if item is None:
            return
        row_index = self.leaderboard_list.row(item)

        def delete_current_row() -> None:
            self._remove_leaderboard_at_row(row_index)

        builder = ContextMenuBuilder(self.leaderboard_list)
        builder.add_action("删除当前行", delete_current_row)
        builder.exec_for(self.leaderboard_list, pos)

    def _on_add_leaderboard_clicked(self) -> None:
        if self._system_payload is None:
            return
        settings = self._get_leaderboard_settings()
        records_any = settings.get("records")
        if not isinstance(records_any, list):
            records_any = []
            settings["records"] = records_any
        records: List[Any] = records_any

        existing_ids: List[str] = []
        for record in records:
            if isinstance(record, dict):
                raw_id = record.get("leaderboard_id")
                if isinstance(raw_id, str) and raw_id:
                    existing_ids.append(raw_id)

        new_id = generate_prefixed_id("leaderboard")
        while new_id in existing_ids:
            new_id = generate_prefixed_id("leaderboard")

        new_index = len(records) + 1
        new_record: Dict[str, Any] = {
            "leaderboard_id": new_id,
            "leaderboard_name": f"排行榜{new_index}",
            "order_index": new_index,
            "display_priority": 1,
            "display_format": "纯数值",
            "reset_type": "不重置",
            "score_sort_rule": "越大越靠前",
        }
        records.append(new_record)
        self.data_updated.emit()

        self._load_tab()
        if self.leaderboard_list.count() > 0:
            self.leaderboard_list.setCurrentRow(self.leaderboard_list.count() - 1)


__all__ = ["PeripheralLeaderboardTab"]


