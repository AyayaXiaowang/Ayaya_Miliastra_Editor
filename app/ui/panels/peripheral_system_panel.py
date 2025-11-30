from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Iterable, Union

from PyQt6 import QtCore, QtWidgets

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from ui.foundation.context_menu_builder import ContextMenuBuilder
from ui.foundation.theme_manager import Sizes
from ui.foundation.toggle_switch import ToggleSwitch
from ui.foundation.id_generator import generate_prefixed_id
from ui.panels.panel_scaffold import PanelScaffold
from ui.panels.package_membership_selector import (
    PackageMembershipSelector,
    build_package_membership_row,
)


ManagementPackage = Union[PackageView, GlobalResourceView]


class PeripheralSystemManagementPanel(PanelScaffold):
    """外围系统管理右侧编辑面板。

    结构约定（与 `ManagementData.peripheral_systems` 对齐）：
    - management.peripheral_systems: {system_id: system_payload, ...}
    - system_payload 字段：
        - system_id: str
        - system_name: str
        - name: str  # 兼容通用展示逻辑
        - description: str
        - leaderboard_settings: {enabled, allow_room_settle, records: [...]}
        - competitive_rank_settings: {enabled, allow_room_settle, note, score_groups: [...]}
        - achievement_settings: {enabled, allow_room_settle, extreme_enabled, items: [...]}
        - last_modified: str

    本面板只负责就地编辑上述结构，实际持久化由 PackageController 统一处理。
    """

    data_updated = QtCore.pyqtSignal()
    # 外围系统所属存档变更 (system_id, package_id, is_checked)
    system_package_membership_changed = QtCore.pyqtSignal(str, str, bool)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="外围系统详情",
            description="配置外围系统模板的排行榜、竞技段位与成就。",
        )

        self.current_package: Optional[ManagementPackage] = None
        self.current_system_id: Optional[str] = None
        self.current_system_payload: Optional[Dict[str, Any]] = None

        # 顶部“所属存档”多选行
        self._package_row_widget: QtWidgets.QWidget
        self._package_label: QtWidgets.QLabel
        self._package_selector: PackageMembershipSelector

        (
            self._package_row_widget,
            self._package_label,
            self._package_selector,
        ) = build_package_membership_row(
            self.body_layout,
            self,
            self._on_package_membership_changed,
            label_text="所属存档:",
        )
        self._package_selector.setEnabled(False)

        self.tabs = QtWidgets.QTabWidget()
        self.body_layout.addWidget(self.tabs, 1)

        self.leaderboard_page = QtWidgets.QWidget()
        self.rank_page = QtWidgets.QWidget()
        self.achievement_page = QtWidgets.QWidget()

        self.tabs.addTab(self.leaderboard_page, "排行榜")
        self.tabs.addTab(self.rank_page, "竞技段位")
        self.tabs.addTab(self.achievement_page, "成就")

        self._build_leaderboard_tab(self.leaderboard_page)
        self._build_rank_tab(self.rank_page)
        self._build_achievement_tab(self.achievement_page)

        self.setEnabled(False)

    # ------------------------------------------------------------------ 公共接口

    def clear(self) -> None:
        """清空当前上下文与表单内容。"""
        self.current_package = None
        self.current_system_id = None
        self.current_system_payload = None

        self._package_selector.clear_membership()
        self._package_selector.setEnabled(False)

        self._set_leaderboard_enabled(False, False)
        self._set_rank_enabled(False, False)
        self._set_achievement_enabled(False, False, False)

        self.leaderboard_list.clear()
        self.rank_group_list.clear()
        self.achievement_list.clear()

        self._clear_leaderboard_form()
        self._clear_rank_group_form()
        self._clear_achievement_form()

        self.setEnabled(False)

    def set_context(self, package: ManagementPackage, system_id: str) -> None:
        """更新当前外围系统模板上下文并刷新三个标签页。"""
        self.current_package = package
        self.current_system_id = system_id

        container_any = package.management.peripheral_systems
        if not isinstance(container_any, dict):
            self.clear()
            return
        payload_any = container_any.get(system_id)
        if not isinstance(payload_any, dict):
            self.clear()
            return

        self.current_system_payload = payload_any
        self._ensure_system_structure()

        system_name_text = str(payload_any.get("system_name", "")).strip() or system_id
        self.set_title(f"外围系统：{system_name_text}")

        self._load_leaderboard_tab()
        self._load_rank_tab()
        self._load_achievement_tab()

        self.setEnabled(True)

    # ------------------------------------------------------------------ 所属存档（外围系统模板）

    def set_current_system_id(self, system_id: Optional[str]) -> None:
        """更新当前正在编辑的外围系统模板 ID，用于在归属变更时发射完整上下文。"""
        self.current_system_id = system_id
        if system_id is None:
            self._package_selector.clear_membership()
            self._package_selector.setEnabled(False)

    def set_packages_and_membership(
        self,
        packages: Sequence[dict],
        membership: Iterable[str],
    ) -> None:
        """根据给定包列表与归属集合更新多选下拉状态。"""
        if not packages:
            self._package_selector.clear_membership()
            self._package_selector.setEnabled(False)
            return
        self._package_selector.set_packages(list(packages))
        self._package_selector.set_membership(set(membership))
        self._package_selector.setEnabled(self.current_system_id is not None)

    def _on_package_membership_changed(self, package_id: str, is_checked: bool) -> None:
        """用户在“所属存档”多选下拉中勾选/取消某个存档时触发。"""
        if not package_id:
            return
        if not self.current_system_id:
            return
        self.system_package_membership_changed.emit(
            self.current_system_id,
            package_id,
            is_checked,
        )

    # ------------------------------------------------------------------ Leaderboard Tab

    def _build_leaderboard_tab(self, page: QtWidgets.QWidget) -> None:
        main_layout = QtWidgets.QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(Sizes.SPACING_MEDIUM)

        scroll_area = QtWidgets.QScrollArea(page)
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
        self.leaderboard_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
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

        # 绑定信号
        self.leaderboard_enabled_switch.stateChanged.connect(self._on_leaderboard_enabled_changed)
        self.leaderboard_allow_room_switch.stateChanged.connect(self._on_leaderboard_allow_room_changed)
        self.leaderboard_list.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.leaderboard_list.customContextMenuRequested.connect(
            self._on_leaderboard_context_menu
        )
        self.leaderboard_list.currentRowChanged.connect(self._on_leaderboard_row_changed)
        self.leaderboard_name_edit.editingFinished.connect(self._apply_leaderboard_form_changes)
        self.leaderboard_index_spin.valueChanged.connect(self._apply_leaderboard_form_changes)
        self.leaderboard_display_priority_spin.valueChanged.connect(self._apply_leaderboard_form_changes)
        self.leaderboard_display_format_combo.currentIndexChanged.connect(
            self._apply_leaderboard_form_changes
        )
        self.leaderboard_reset_type_combo.currentIndexChanged.connect(self._apply_leaderboard_form_changes)
        self.leaderboard_sort_rule_combo.currentIndexChanged.connect(self._apply_leaderboard_form_changes)
        self.add_leaderboard_button.clicked.connect(self._on_add_leaderboard_clicked)
        self.remove_leaderboard_button.clicked.connect(self._on_remove_leaderboard_clicked)

    def _load_leaderboard_tab(self) -> None:
        config = self._get_leaderboard_settings()
        enabled_flag = bool(config.get("enabled", False))
        allow_room_flag = bool(config.get("allow_room_settle", False))
        self._set_leaderboard_enabled(enabled_flag, allow_room_flag)

        self.leaderboard_list.blockSignals(True)
        self.leaderboard_list.clear()
        records_any = config.get("records", [])
        records: List[Dict[str, Any]] = [
            entry for entry in records_any if isinstance(entry, dict)
        ]
        for record in records:
            raw_name = record.get("leaderboard_name") or record.get("name") or record.get("leaderboard_id", "")
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

    def _get_leaderboard_settings(self) -> Dict[str, Any]:
        if self.current_system_payload is None:
            return {}
        config_any = self.current_system_payload.get("leaderboard_settings")
        if not isinstance(config_any, dict):
            config_any = {
                "enabled": False,
                "allow_room_settle": False,
                "records": [],
            }
            self.current_system_payload["leaderboard_settings"] = config_any
        return config_any

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
        config = self._get_leaderboard_settings()
        records_any = config.get("records", [])
        if not isinstance(records_any, list) or row_index < 0 or row_index >= len(records_any):
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

        def _set_combo_by_text(combo: QtWidgets.QComboBox, text: str) -> None:
            index = combo.findText(text)
            if index < 0:
                index = 0
            combo.setCurrentIndex(index)

        _set_combo_by_text(self.leaderboard_display_format_combo, display_format_value)
        _set_combo_by_text(self.leaderboard_reset_type_combo, reset_type_value)
        _set_combo_by_text(self.leaderboard_sort_rule_combo, sort_rule_value)

        self.leaderboard_name_edit.blockSignals(False)
        self.leaderboard_index_spin.blockSignals(False)
        self.leaderboard_display_priority_spin.blockSignals(False)
        self.leaderboard_display_format_combo.blockSignals(False)
        self.leaderboard_reset_type_combo.blockSignals(False)
        self.leaderboard_sort_rule_combo.blockSignals(False)

    def _on_leaderboard_enabled_changed(self, state: int) -> None:
        if self.current_system_payload is None:
            return
        enabled_flag = state == QtCore.Qt.CheckState.Checked.value
        config = self._get_leaderboard_settings()
        config["enabled"] = bool(enabled_flag)
        self._mark_system_modified()

    def _on_leaderboard_allow_room_changed(self, state: int) -> None:
        if self.current_system_payload is None:
            return
        allow_flag = state == QtCore.Qt.CheckState.Checked.value
        config = self._get_leaderboard_settings()
        config["allow_room_settle"] = bool(allow_flag)
        self._mark_system_modified()

    def _on_leaderboard_row_changed(self, row_index: int) -> None:
        self._load_leaderboard_form_for_row(row_index)

    def _apply_leaderboard_form_changes(self) -> None:
        if self.current_system_payload is None:
            return
        current_row = self.leaderboard_list.currentRow()
        if current_row < 0:
            return
        config = self._get_leaderboard_settings()
        records_any = config.get("records", [])
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

        self._mark_system_modified()

    def _remove_leaderboard_at_row(self, row_index: int) -> None:
        if self.current_system_payload is None:
            return
        if row_index < 0:
            return
        config = self._get_leaderboard_settings()
        records_any = config.get("records")
        if not isinstance(records_any, list):
            return
        if row_index >= len(records_any):
            return
        del records_any[row_index]
        self._mark_system_modified()
        self._load_leaderboard_tab()
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
        if self.current_system_payload is None:
            return
        config = self._get_leaderboard_settings()
        records_any = config.get("records")
        if not isinstance(records_any, list):
            records_any = []
            config["records"] = records_any
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
        self._mark_system_modified()

        self._load_leaderboard_tab()
        if self.leaderboard_list.count() > 0:
            self.leaderboard_list.setCurrentRow(self.leaderboard_list.count() - 1)

    # ------------------------------------------------------------------ Rank Tab

    def _build_rank_tab(self, page: QtWidgets.QWidget) -> None:
        main_layout = QtWidgets.QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(Sizes.SPACING_MEDIUM)

        scroll_area = QtWidgets.QScrollArea(page)
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
        self.rank_group_list.customContextMenuRequested.connect(
            self._on_rank_group_context_menu
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

        # 绑定信号
        self.rank_enabled_switch.stateChanged.connect(self._on_rank_enabled_changed)
        self.rank_allow_room_switch.stateChanged.connect(self._on_rank_allow_room_changed)
        self.rank_announcement_edit.textChanged.connect(self._on_rank_announcement_changed)
        self.rank_group_list.currentRowChanged.connect(self._on_rank_group_row_changed)
        self.rank_group_name_edit.editingFinished.connect(self._apply_rank_group_form_changes)
        self.rank_group_index_spin.valueChanged.connect(self._apply_rank_group_form_changes)
        self.rank_victory_score_spin.valueChanged.connect(self._apply_rank_group_form_changes)
        self.rank_defeat_score_spin.valueChanged.connect(self._apply_rank_group_form_changes)
        self.rank_unsettled_score_spin.valueChanged.connect(self._apply_rank_group_form_changes)
        self.rank_escape_score_spin.valueChanged.connect(self._apply_rank_group_form_changes)
        self.rank_applied_players_combo.currentIndexChanged.connect(self._apply_rank_group_form_changes)
        self.add_rank_group_button.clicked.connect(self._on_add_rank_group_clicked)
        self.remove_rank_group_button.clicked.connect(self._on_remove_rank_group_clicked)

    def _load_rank_tab(self) -> None:
        config = self._get_rank_settings()
        enabled_flag = bool(config.get("enabled", False))
        allow_room_flag = bool(config.get("allow_room_settle", False))
        note_text = str(config.get("note", "")).strip()

        self._set_rank_enabled(enabled_flag, allow_room_flag)
        self.rank_announcement_edit.blockSignals(True)
        self.rank_announcement_edit.setPlainText(note_text)
        self.rank_announcement_edit.blockSignals(False)

        self.rank_group_list.blockSignals(True)
        self.rank_group_list.clear()
        groups_any = config.get("score_groups", [])
        groups: List[Dict[str, Any]] = [entry for entry in groups_any if isinstance(entry, dict)]
        for group in groups:
            raw_name = group.get("group_name") or group.get("name") or group.get("group_index", "")
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

    def _get_rank_settings(self) -> Dict[str, Any]:
        if self.current_system_payload is None:
            return {}
        config_any = self.current_system_payload.get("competitive_rank_settings")
        if not isinstance(config_any, dict):
            config_any = {
                "enabled": False,
                "allow_room_settle": False,
                "note": "",
                "score_groups": [],
            }
            self.current_system_payload["competitive_rank_settings"] = config_any
        return config_any

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
        config = self._get_rank_settings()
        groups_any = config.get("score_groups", [])
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

    def _on_rank_enabled_changed(self, state: int) -> None:
        if self.current_system_payload is None:
            return
        enabled_flag = state == QtCore.Qt.CheckState.Checked.value
        config = self._get_rank_settings()
        config["enabled"] = bool(enabled_flag)
        self._mark_system_modified()

    def _on_rank_allow_room_changed(self, state: int) -> None:
        if self.current_system_payload is None:
            return
        allow_flag = state == QtCore.Qt.CheckState.Checked.value
        config = self._get_rank_settings()
        config["allow_room_settle"] = bool(allow_flag)
        self._mark_system_modified()

    def _on_rank_announcement_changed(self) -> None:
        if self.current_system_payload is None:
            return
        config = self._get_rank_settings()
        config["note"] = self.rank_announcement_edit.toPlainText().strip()
        self._mark_system_modified()

    def _on_rank_group_row_changed(self, row_index: int) -> None:
        self._load_rank_group_form_for_row(row_index)

    def _apply_rank_group_form_changes(self) -> None:
        if self.current_system_payload is None:
            return
        current_row = self.rank_group_list.currentRow()
        if current_row < 0:
            return
        config = self._get_rank_settings()
        groups_any = config.get("score_groups", [])
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

        self._mark_system_modified()

    def _remove_rank_group_at_row(self, row_index: int) -> None:
        if self.current_system_payload is None:
            return
        if row_index < 0:
            return
        config = self._get_rank_settings()
        groups_any = config.get("score_groups")
        if not isinstance(groups_any, list):
            return
        if row_index >= len(groups_any):
            return
        del groups_any[row_index]
        self._mark_system_modified()
        self._load_rank_tab()
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
        if self.current_system_payload is None:
            return
        config = self._get_rank_settings()
        groups_any = config.get("score_groups")
        if not isinstance(groups_any, list):
            groups_any = []
            config["score_groups"] = groups_any
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
        self._mark_system_modified()

        self._load_rank_tab()
        if self.rank_group_list.count() > 0:
            self.rank_group_list.setCurrentRow(self.rank_group_list.count() - 1)

    # ------------------------------------------------------------------ Achievement Tab

    def _build_achievement_tab(self, page: QtWidgets.QWidget) -> None:
        main_layout = QtWidgets.QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(Sizes.SPACING_MEDIUM)

        scroll_area = QtWidgets.QScrollArea(page)
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
        self.achievement_list.customContextMenuRequested.connect(
            self._on_achievement_context_menu
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

        # 绑定信号
        self.achievement_enabled_switch.stateChanged.connect(self._on_achievement_enabled_changed)
        self.achievement_allow_room_switch.stateChanged.connect(self._on_achievement_allow_room_changed)
        self.achievement_extreme_switch.stateChanged.connect(self._on_achievement_extreme_changed)
        self.achievement_list.currentRowChanged.connect(self._on_achievement_row_changed)
        self.achievement_name_edit.editingFinished.connect(self._apply_achievement_form_changes)
        self.achievement_index_spin.valueChanged.connect(self._apply_achievement_form_changes)
        self.achievement_description_edit.textChanged.connect(self._apply_achievement_form_changes)
        self.achievement_icon_edit.editingFinished.connect(self._apply_achievement_form_changes)
        self.add_achievement_button.clicked.connect(self._on_add_achievement_clicked)
        self.remove_achievement_button.clicked.connect(self._on_remove_achievement_clicked)

    def _load_achievement_tab(self) -> None:
        config = self._get_achievement_settings()
        enabled_flag = bool(config.get("enabled", False))
        allow_room_flag = bool(config.get("allow_room_settle", False))
        extreme_flag = bool(config.get("extreme_enabled", False))

        self._set_achievement_enabled(enabled_flag, allow_room_flag, extreme_flag)

        self.achievement_list.blockSignals(True)
        self.achievement_list.clear()
        items_any = config.get("items", [])
        items: List[Dict[str, Any]] = [entry for entry in items_any if isinstance(entry, dict)]
        for item in items:
            raw_name = item.get("achievement_name") or item.get("name") or item.get("achievement_id", "")
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

    def _get_achievement_settings(self) -> Dict[str, Any]:
        if self.current_system_payload is None:
            return {}
        config_any = self.current_system_payload.get("achievement_settings")
        if not isinstance(config_any, dict):
            config_any = {
                "enabled": False,
                "allow_room_settle": False,
                "extreme_enabled": False,
                "items": [],
            }
            self.current_system_payload["achievement_settings"] = config_any
        return config_any

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
        config = self._get_achievement_settings()
        items_any = config.get("items", [])
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

    def _on_achievement_enabled_changed(self, state: int) -> None:
        if self.current_system_payload is None:
            return
        enabled_flag = state == QtCore.Qt.CheckState.Checked.value
        config = self._get_achievement_settings()
        config["enabled"] = bool(enabled_flag)
        self._mark_system_modified()

    def _on_achievement_allow_room_changed(self, state: int) -> None:
        if self.current_system_payload is None:
            return
        allow_flag = state == QtCore.Qt.CheckState.Checked.value
        config = self._get_achievement_settings()
        config["allow_room_settle"] = bool(allow_flag)
        self._mark_system_modified()

    def _on_achievement_extreme_changed(self, state: int) -> None:
        if self.current_system_payload is None:
            return
        extreme_flag = state == QtCore.Qt.CheckState.Checked.value
        config = self._get_achievement_settings()
        config["extreme_enabled"] = bool(extreme_flag)
        self._mark_system_modified()

    def _on_achievement_row_changed(self, row_index: int) -> None:
        self._load_achievement_form_for_row(row_index)

    def _apply_achievement_form_changes(self) -> None:
        if self.current_system_payload is None:
            return
        current_row = self.achievement_list.currentRow()
        if current_row < 0:
            return
        config = self._get_achievement_settings()
        items_any = config.get("items", [])
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

        self._mark_system_modified()

    def _remove_achievement_at_row(self, row_index: int) -> None:
        if self.current_system_payload is None:
            return
        if row_index < 0:
            return
        config = self._get_achievement_settings()
        items_any = config.get("items")
        if not isinstance(items_any, list):
            return
        if row_index >= len(items_any):
            return
        del items_any[row_index]
        self._mark_system_modified()
        self._load_achievement_tab()
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
        if self.current_system_payload is None:
            return
        config = self._get_achievement_settings()
        items_any = config.get("items")
        if not isinstance(items_any, list):
            items_any = []
            config["items"] = items_any
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
        self._mark_system_modified()

        self._load_achievement_tab()
        if self.achievement_list.count() > 0:
            self.achievement_list.setCurrentRow(self.achievement_list.count() - 1)

    # ------------------------------------------------------------------ 内部工具

    def _ensure_system_structure(self) -> None:
        """确保当前模板下的三个子配置体结构存在。"""
        if self.current_system_payload is None:
            return

        payload = self.current_system_payload

        system_id_text = str(payload.get("system_id", self.current_system_id or "")).strip()
        if not system_id_text and self.current_system_id:
            system_id_text = self.current_system_id
            payload["system_id"] = system_id_text

        system_name_text = str(payload.get("system_name", "")).strip()
        if not system_name_text and system_id_text:
            system_name_text = system_id_text
            payload["system_name"] = system_name_text
        if "name" not in payload:
            payload["name"] = system_name_text or system_id_text

        for key, default_value in [
            (
                "leaderboard_settings",
                {"enabled": False, "allow_room_settle": False, "records": []},
            ),
            (
                "competitive_rank_settings",
                {
                    "enabled": False,
                    "allow_room_settle": False,
                    "note": "",
                    "score_groups": [],
                },
            ),
            (
                "achievement_settings",
                {
                    "enabled": False,
                    "allow_room_settle": False,
                    "extreme_enabled": False,
                    "items": [],
                },
            ),
        ]:
            value_any = payload.get(key)
            if not isinstance(value_any, dict):
                payload[key] = dict(default_value)

    def _mark_system_modified(self) -> None:
        if self.current_system_payload is None:
            return
        self.current_system_payload["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.data_updated.emit()


__all__ = ["PeripheralSystemManagementPanel"]


