from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.toggle_switch import ToggleSwitch


class PeripheralAchievementTab(QtWidgets.QWidget):
    """外围系统：成就 Tab（就地编辑 system_payload['achievement_settings']）。"""

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
        self._set_achievement_enabled(False, False, False)
        self.achievement_list.clear()
        self._clear_achievement_form()
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

        settings_group = QtWidgets.QGroupBox("成就设置")
        settings_layout = QtWidgets.QFormLayout(settings_group)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setHorizontalSpacing(Sizes.SPACING_SMALL)
        settings_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        self.achievement_enabled_switch = ToggleSwitch()
        self.achievement_allow_room_switch = ToggleSwitch()
        self.achievement_extreme_switch = ToggleSwitch()

        settings_layout.addRow("是否开启成就:", self.achievement_enabled_switch)
        settings_layout.addRow("允许房间内游玩结算成就:", self.achievement_allow_room_switch)
        settings_layout.addRow("极致成就:", self.achievement_extreme_switch)
        scroll_layout.addWidget(settings_group)

        list_group = QtWidgets.QGroupBox("成就列表")
        list_group.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )
        list_layout = QtWidgets.QVBoxLayout(list_group)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(Sizes.SPACING_SMALL)

        self.achievement_list = QtWidgets.QListWidget()
        self.achievement_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.achievement_list.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        list_layout.addWidget(self.achievement_list)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setHorizontalSpacing(Sizes.SPACING_SMALL)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        self.achievement_name_edit = QtWidgets.QLineEdit()
        self.achievement_index_spin = QtWidgets.QSpinBox()
        self.achievement_index_spin.setRange(1, 9999)
        self.achievement_description_edit = QtWidgets.QTextEdit()
        self.achievement_description_edit.setMinimumHeight(80)
        self.achievement_description_edit.setMaximumHeight(200)
        self.achievement_icon_edit = QtWidgets.QLineEdit()

        form_layout.addRow("成就名称:", self.achievement_name_edit)
        form_layout.addRow("序号:", self.achievement_index_spin)
        form_layout.addRow("描述:", self.achievement_description_edit)
        form_layout.addRow("图标路径:", self.achievement_icon_edit)

        list_layout.addLayout(form_layout)
        scroll_layout.addWidget(list_group)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        self.add_achievement_button = QtWidgets.QPushButton("新建成就")
        self.remove_achievement_button = QtWidgets.QPushButton("删除选中")
        button_row.addWidget(self.add_achievement_button)
        button_row.addWidget(self.remove_achievement_button)
        scroll_layout.addLayout(button_row)

        scroll_layout.addStretch(1)
        scroll_area.setWidget(container)

    def _bind_signals(self) -> None:
        self.achievement_enabled_switch.stateChanged.connect(
            self._on_achievement_enabled_changed
        )
        self.achievement_allow_room_switch.stateChanged.connect(
            self._on_achievement_allow_room_changed
        )
        self.achievement_extreme_switch.stateChanged.connect(
            self._on_achievement_extreme_changed
        )

        self.achievement_list.customContextMenuRequested.connect(
            self._on_achievement_context_menu
        )
        self.achievement_list.currentRowChanged.connect(self._on_achievement_row_changed)

        self.achievement_name_edit.editingFinished.connect(
            self._apply_achievement_form_changes
        )
        self.achievement_index_spin.valueChanged.connect(self._apply_achievement_form_changes)
        self.achievement_description_edit.textChanged.connect(
            self._apply_achievement_form_changes
        )
        self.achievement_icon_edit.editingFinished.connect(
            self._apply_achievement_form_changes
        )

        self.add_achievement_button.clicked.connect(self._on_add_achievement_clicked)
        self.remove_achievement_button.clicked.connect(self._on_remove_achievement_clicked)

    # ------------------------------ Data helpers

    def _get_achievement_settings(self) -> Dict[str, Any]:
        if self._system_payload is None:
            return {}
        settings_any = self._system_payload.get("achievement_settings")
        if not isinstance(settings_any, dict):
            settings_any = {
                "enabled": False,
                "allow_room_settle": False,
                "extreme_enabled": False,
                "items": [],
            }
            self._system_payload["achievement_settings"] = settings_any
        return settings_any

    def _load_tab(self) -> None:
        settings = self._get_achievement_settings()
        enabled_flag = bool(settings.get("enabled", False))
        allow_room_flag = bool(settings.get("allow_room_settle", False))
        extreme_flag = bool(settings.get("extreme_enabled", False))

        self._set_achievement_enabled(enabled_flag, allow_room_flag, extreme_flag)

        self.achievement_list.blockSignals(True)
        self.achievement_list.clear()
        items_any = settings.get("items", [])
        items: List[Dict[str, Any]] = [entry for entry in items_any if isinstance(entry, dict)]
        for item in items:
            raw_name = item.get("achievement_name") or item.get("name") or item.get(
                "achievement_id", ""
            )
            display_name = str(raw_name) if raw_name is not None else ""
            if not display_name:
                display_name = "未命名成就"
            self.achievement_list.addItem(display_name)
        self.achievement_list.blockSignals(False)

        if self.achievement_list.count() > 0:
            self.achievement_list.setCurrentRow(0)
            self._load_achievement_form_for_row(0)
        else:
            self._clear_achievement_form()

    def _set_achievement_enabled(self, enabled: bool, allow_room: bool, extreme: bool) -> None:
        self.achievement_enabled_switch.blockSignals(True)
        self.achievement_allow_room_switch.blockSignals(True)
        self.achievement_extreme_switch.blockSignals(True)

        self.achievement_enabled_switch.setChecked(enabled)
        self.achievement_allow_room_switch.setChecked(allow_room)
        self.achievement_extreme_switch.setChecked(extreme)

        self.achievement_enabled_switch.blockSignals(False)
        self.achievement_allow_room_switch.blockSignals(False)
        self.achievement_extreme_switch.blockSignals(False)

    def _clear_achievement_form(self) -> None:
        self.achievement_name_edit.blockSignals(True)
        self.achievement_index_spin.blockSignals(True)
        self.achievement_description_edit.blockSignals(True)
        self.achievement_icon_edit.blockSignals(True)

        self.achievement_name_edit.clear()
        self.achievement_index_spin.setValue(1)
        self.achievement_description_edit.setPlainText("")
        self.achievement_icon_edit.clear()

        self.achievement_name_edit.blockSignals(False)
        self.achievement_index_spin.blockSignals(False)
        self.achievement_description_edit.blockSignals(False)
        self.achievement_icon_edit.blockSignals(False)

    def _load_achievement_form_for_row(self, row_index: int) -> None:
        settings = self._get_achievement_settings()
        items_any = settings.get("items", [])
        if not isinstance(items_any, list) or row_index < 0 or row_index >= len(items_any):
            self._clear_achievement_form()
            return
        item_any = items_any[row_index]
        if not isinstance(item_any, dict):
            self._clear_achievement_form()
            return
        item: Dict[str, Any] = item_any

        name_text = str(item.get("achievement_name", "")).strip()
        index_value = int(item.get("order_index", row_index + 1))
        description_text = str(item.get("description", "")).strip()
        icon_text = str(item.get("icon", "")).strip()

        self.achievement_name_edit.blockSignals(True)
        self.achievement_index_spin.blockSignals(True)
        self.achievement_description_edit.blockSignals(True)
        self.achievement_icon_edit.blockSignals(True)

        self.achievement_name_edit.setText(name_text)
        self.achievement_index_spin.setValue(index_value)
        self.achievement_description_edit.setPlainText(description_text)
        self.achievement_icon_edit.setText(icon_text)

        self.achievement_name_edit.blockSignals(False)
        self.achievement_index_spin.blockSignals(False)
        self.achievement_description_edit.blockSignals(False)
        self.achievement_icon_edit.blockSignals(False)

    # ------------------------------ Event handlers

    def _on_achievement_enabled_changed(self, state: int) -> None:
        if self._system_payload is None:
            return
        enabled_flag = state == QtCore.Qt.CheckState.Checked.value
        settings = self._get_achievement_settings()
        settings["enabled"] = bool(enabled_flag)
        self.data_updated.emit()

    def _on_achievement_allow_room_changed(self, state: int) -> None:
        if self._system_payload is None:
            return
        allow_flag = state == QtCore.Qt.CheckState.Checked.value
        settings = self._get_achievement_settings()
        settings["allow_room_settle"] = bool(allow_flag)
        self.data_updated.emit()

    def _on_achievement_extreme_changed(self, state: int) -> None:
        if self._system_payload is None:
            return
        extreme_flag = state == QtCore.Qt.CheckState.Checked.value
        settings = self._get_achievement_settings()
        settings["extreme_enabled"] = bool(extreme_flag)
        self.data_updated.emit()

    def _on_achievement_row_changed(self, row_index: int) -> None:
        self._load_achievement_form_for_row(row_index)

    def _apply_achievement_form_changes(self) -> None:
        if self._system_payload is None:
            return
        current_row = self.achievement_list.currentRow()
        if current_row < 0:
            return
        settings = self._get_achievement_settings()
        items_any = settings.get("items", [])
        if not isinstance(items_any, list) or current_row >= len(items_any):
            return
        item_any = items_any[current_row]
        if not isinstance(item_any, dict):
            return
        item: Dict[str, Any] = item_any

        name_text = self.achievement_name_edit.text().strip()
        index_value = int(self.achievement_index_spin.value())
        description_text = self.achievement_description_edit.toPlainText().strip()
        icon_text = self.achievement_icon_edit.text().strip()

        if name_text:
            item["achievement_name"] = name_text
        item["order_index"] = index_value
        item["description"] = description_text
        item["icon"] = icon_text

        list_item = self.achievement_list.item(current_row)
        if list_item is not None:
            list_item.setText(name_text or "未命名成就")

        self.data_updated.emit()

    def _remove_achievement_at_row(self, row_index: int) -> None:
        if self._system_payload is None:
            return
        if row_index < 0:
            return
        settings = self._get_achievement_settings()
        items_any = settings.get("items")
        if not isinstance(items_any, list):
            return
        if row_index >= len(items_any):
            return
        del items_any[row_index]
        self.data_updated.emit()
        self._load_tab()
        if self.achievement_list.count() > 0:
            next_row = min(row_index, self.achievement_list.count() - 1)
            self.achievement_list.setCurrentRow(next_row)

    def _on_remove_achievement_clicked(self) -> None:
        current_row = self.achievement_list.currentRow()
        self._remove_achievement_at_row(current_row)

    def _on_achievement_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.achievement_list.itemAt(pos)
        if item is None:
            return
        row_index = self.achievement_list.row(item)

        def delete_current_row() -> None:
            self._remove_achievement_at_row(row_index)

        builder = ContextMenuBuilder(self.achievement_list)
        builder.add_action("删除当前行", delete_current_row)
        builder.exec_for(self.achievement_list, pos)

    def _on_add_achievement_clicked(self) -> None:
        if self._system_payload is None:
            return
        settings = self._get_achievement_settings()
        items_any = settings.get("items")
        if not isinstance(items_any, list):
            items_any = []
            settings["items"] = items_any
        items: List[Any] = items_any

        existing_ids: List[str] = []
        for entry in items:
            if isinstance(entry, dict):
                raw_id = entry.get("achievement_id")
                if isinstance(raw_id, str) and raw_id:
                    existing_ids.append(raw_id)

        new_id = generate_prefixed_id("achievement")
        while new_id in existing_ids:
            new_id = generate_prefixed_id("achievement")

        new_index = len(items) + 1
        new_item: Dict[str, Any] = {
            "achievement_id": new_id,
            "achievement_name": f"成就{new_index}",
            "order_index": new_index,
            "description": "",
            "icon": "",
        }
        items.append(new_item)
        self.data_updated.emit()

        self._load_tab()
        if self.achievement_list.count() > 0:
            self.achievement_list.setCurrentRow(self.achievement_list.count() - 1)


__all__ = ["PeripheralAchievementTab"]


