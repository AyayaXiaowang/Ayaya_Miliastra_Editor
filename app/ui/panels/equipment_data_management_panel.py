from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence, Union

from PyQt6 import QtCore, QtWidgets

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from app.ui.foundation import dialog_utils
from app.ui.foundation.theme_manager import Sizes, ThemeManager
from app.ui.panels.package_membership_selector import (
    PackageMembershipSelector,
    build_package_membership_row,
)
from app.ui.panels.panel_scaffold import PanelScaffold


ManagementPackage = Union[PackageView, GlobalResourceView]


class BaseEquipmentConfigPanel(PanelScaffold):
    """装备配置通用右侧面板基类（带“所属存档”多选行）。

    子类负责具体字段的表单布局与读写逻辑，本基类只管理：
    - 当前 (package, storage_id, payload) 上下文；
    - 顶部“所属存档”多选行与成员变更信号；
    - 清空/启用状态切换与保存后的 data_updated 事件。
    """

    # 任一字段保存成功后触发，由主窗口统一刷新列表并落盘。
    data_updated = QtCore.pyqtSignal()
    # 资源所属存档变更 (storage_id, package_id, is_checked)
    package_membership_changed = QtCore.pyqtSignal(str, str, bool)

    def __init__(self, parent: Optional[QtWidgets.QWidget], *, title: str, description: str) -> None:
        super().__init__(parent, title=title, description=description)

        self.current_package: Optional[ManagementPackage] = None
        self.current_storage_id: Optional[str] = None
        self.current_payload: Optional[Dict[str, Any]] = None

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

    # ------------------------------------------------------------------ 公共接口

    def clear(self) -> None:
        """清空当前上下文并重置表单。"""
        self.current_package = None
        self.current_storage_id = None
        self.current_payload = None

        if self._package_selector is not None:
            self._package_selector.clear_membership()
            self._package_selector.setEnabled(False)

        self._clear_form()
        self.setEnabled(False)

    def set_packages_and_membership(
        self,
        packages: Sequence[dict],
        membership: Iterable[str],
    ) -> None:
        """更新顶部“所属存档”多选行。"""
        selector: Optional[PackageMembershipSelector] = self._package_selector
        if selector is None:
            return
        if not packages:
            selector.clear_membership()
            selector.setEnabled(False)
            return
        selector.set_packages(list(packages))
        selector.set_membership(set(membership))
        selector.setEnabled(self.current_storage_id is not None)

    def set_current_storage_id(self, storage_id: Optional[str]) -> None:
        """仅更新当前正在编辑的存储ID，不改变 payload。"""
        self.current_storage_id = storage_id
        if storage_id is None and self._package_selector is not None:
            self._package_selector.clear_membership()
            self._package_selector.setEnabled(False)

    # ------------------------------------------------------------------ 供子类复用的上下文绑定

    def _set_context_internal(
        self,
        package: ManagementPackage,
        storage_id: str,
        payload: Dict[str, Any],
    ) -> None:
        """在子类完成类型判定后调用，统一完成上下文绑定与表单加载。"""
        self.current_package = package
        self.current_storage_id = storage_id
        self.current_payload = payload
        self._load_from_payload(storage_id, payload)
        self.setEnabled(True)

    def _on_package_membership_changed(self, package_id: str, is_checked: bool) -> None:
        if not package_id:
            return
        if not self.current_storage_id:
            return
        self.package_membership_changed.emit(self.current_storage_id, package_id, is_checked)

    # ------------------------------------------------------------------ 需要子类实现的钩子

    def _clear_form(self) -> None:
        raise NotImplementedError

    def _load_from_payload(self, storage_id: str, payload: Dict[str, Any]) -> None:
        _ = (storage_id, payload)
        raise NotImplementedError


class EquipmentEntryManagementPanel(BaseEquipmentConfigPanel):
    """装备词条详情面板。

    用于编辑 equipment_entries Section 中选中记录的主要字段：
    - 词条名称 / 配置ID（纯数字、用户可编辑）；
    - 生效时机 / 词条类型 / 属性与加成方式；
    - 固定加成值与随机范围；
    - 描述类型与自定义描述文案。
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="装备词条详情",
            description="编辑装备词条的配置ID、加成方式与展示文案。",
        )

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        form_container = QtWidgets.QWidget(scroll_area)
        form_layout = QtWidgets.QFormLayout(form_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        scroll_area.setWidget(form_container)
        self.body_layout.addWidget(scroll_area, 1)

        # --- 基础信息 --------------------------------------------------------
        self.entry_id_label = QtWidgets.QLabel("-")
        form_layout.addRow("存储ID:", self.entry_id_label)

        self.entry_name_edit = QtWidgets.QLineEdit()
        form_layout.addRow("词条名称:", self.entry_name_edit)

        self.config_id_edit = QtWidgets.QLineEdit()
        self.config_id_edit.setPlaceholderText("纯数字配置ID，例如 1132462081")
        form_layout.addRow("配置ID:", self.config_id_edit)

        # --- 生效逻辑 --------------------------------------------------------
        self.effect_timing_combo = QtWidgets.QComboBox()
        self.effect_timing_combo.addItems(["获取时生效", "装备时生效"])
        form_layout.addRow("生效时机:", self.effect_timing_combo)

        self.entry_type_combo = QtWidgets.QComboBox()
        self.entry_type_combo.addItems(["基础属性加成", "赋予节点图", "赋予单位状态"])
        form_layout.addRow("词条类型:", self.entry_type_combo)

        # --- 属性加成 --------------------------------------------------------
        self.attribute_options: list[str] = [
            "生命值修正值",
            "生命值调整率",
            "攻击力修正值",
            "攻击力调整率",
            "防御力修正值",
            "防御力调整率",
            "火元素抗性调整率",
            "雷元素抗性调整率",
            "水元素抗性调整率",
            "草元素抗性调整率",
            "风元素抗性调整率",
            "岩元素抗性调整率",
            "冰元素抗性调整率",
            "暴击触发变更量",
            "暴击伤害变更量",
            "恢复效果调整率",
            "受恢复效果调整率",
            "火元素增伤调整率",
            "雷元素增伤调整率",
            "水元素增伤调整率",
            "草元素增伤调整率",
            "风元素增伤调整率",
            "岩元素增伤调整率",
            "冰元素增伤调整率",
            "物理增伤调整率",
        ]

        self.attribute_type_combo = QtWidgets.QComboBox()
        self.attribute_type_combo.setEditable(False)
        self.attribute_type_combo.addItem("请选择属性", "")
        self.attribute_type_combo.addItems(self.attribute_options)
        form_layout.addRow("选择属性:", self.attribute_type_combo)

        self.bonus_type_combo = QtWidgets.QComboBox()
        self.bonus_type_combo.addItems(["固定值", "随机值"])
        form_layout.addRow("加成类型:", self.bonus_type_combo)

        random_range_layout = QtWidgets.QHBoxLayout()
        self.random_min_spin = QtWidgets.QDoubleSpinBox()
        self.random_min_spin.setRange(-999999.0, 999999.0)
        self.random_min_spin.setDecimals(2)
        self.random_min_spin.setSingleStep(1.0)
        self.random_max_spin = QtWidgets.QDoubleSpinBox()
        self.random_max_spin.setRange(-999999.0, 999999.0)
        self.random_max_spin.setDecimals(2)
        self.random_max_spin.setSingleStep(1.0)
        random_range_layout.addWidget(self.random_min_spin)
        random_range_layout.addWidget(QtWidgets.QLabel(" - "))
        random_range_layout.addWidget(self.random_max_spin)
        random_range_widget = QtWidgets.QWidget()
        random_range_widget.setLayout(random_range_layout)
        form_layout.addRow("随机值范围:", random_range_widget)

        self.fixed_bonus_spin = QtWidgets.QDoubleSpinBox()
        self.fixed_bonus_spin.setRange(-999999.0, 999999.0)
        self.fixed_bonus_spin.setDecimals(2)
        self.fixed_bonus_spin.setSingleStep(1.0)
        form_layout.addRow("固定加成值:", self.fixed_bonus_spin)

        # --- 描述与展示 ------------------------------------------------------
        self.description_type_combo = QtWidgets.QComboBox()
        self.description_type_combo.addItems(["固定描述", "自定义描述"])
        form_layout.addRow("描述类型:", self.description_type_combo)

        self.preview_label = QtWidgets.QLabel("（根据当前配置生成的展示文本预览）")
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet(ThemeManager.info_label_style())
        form_layout.addRow("显示文本内容:", self.preview_label)

        self.custom_description_edit = QtWidgets.QPlainTextEdit()
        self.custom_description_edit.setPlaceholderText("例如：生命值加成{3:f}点")
        self.custom_description_edit.setMinimumHeight(80)
        self.custom_description_edit.setMaximumHeight(200)
        form_layout.addRow("文本内容:", self.custom_description_edit)

        # --- 引用列表（暂时只展示占位说明） -----------------------------------
        reference_group = QtWidgets.QGroupBox("引用列表")
        reference_layout = QtWidgets.QVBoxLayout(reference_group)
        reference_layout.setContentsMargins(0, 0, 0, 0)
        self.reference_label = QtWidgets.QLabel("暂无引用的装备")
        self.reference_label.setWordWrap(True)
        self.reference_label.setEnabled(False)
        reference_layout.addWidget(self.reference_label)
        form_layout.addRow(reference_group)

        # --- 操作按钮 --------------------------------------------------------
        button_row = QtWidgets.QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addStretch(1)
        self.save_button = QtWidgets.QPushButton("保存词条")
        self.save_button.setMinimumHeight(Sizes.BUTTON_HEIGHT)
        self.save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_button)
        self.body_layout.addLayout(button_row)

        self.setEnabled(False)

    # ------------------------------------------------------------------ Base hooks

    def _clear_form(self) -> None:
        self.entry_id_label.setText("-")
        self.entry_name_edit.clear()
        self.config_id_edit.clear()
        self.effect_timing_combo.setCurrentIndex(0)
        self.entry_type_combo.setCurrentIndex(0)
        self.attribute_type_combo.setCurrentIndex(0)
        self.bonus_type_combo.setCurrentIndex(0)
        self.random_min_spin.setValue(0.0)
        self.random_max_spin.setValue(0.0)
        self.fixed_bonus_spin.setValue(0.0)
        self.description_type_combo.setCurrentIndex(0)
        self.preview_label.setText("（根据当前配置生成的展示文本预览）")
        self.custom_description_edit.clear()
        self.reference_label.setText("暂无引用的装备")

    def _load_from_payload(self, storage_id: str, payload: Dict[str, Any]) -> None:
        self.entry_id_label.setText(str(storage_id))

        entry_name_value = str(payload.get("entry_name", ""))
        self.entry_name_edit.setText(entry_name_value)

        config_id_raw = payload.get("config_id", "")
        self.config_id_edit.setText(str(config_id_raw))

        effect_timing_text = str(payload.get("effect_timing", "获取时生效"))
        index_for_timing = self.effect_timing_combo.findText(effect_timing_text)
        if index_for_timing == -1:
            index_for_timing = 0
        self.effect_timing_combo.setCurrentIndex(index_for_timing)

        entry_type_text = str(payload.get("entry_type", "基础属性加成"))
        index_for_type = self.entry_type_combo.findText(entry_type_text)
        if index_for_type == -1:
            index_for_type = 0
        self.entry_type_combo.setCurrentIndex(index_for_type)

        attribute_type_value = str(payload.get("attribute_type", ""))
        if attribute_type_value and attribute_type_value not in self.attribute_options:
            self.attribute_type_combo.addItem(attribute_type_value)
        if attribute_type_value:
            self.attribute_type_combo.setCurrentText(attribute_type_value)
        else:
            self.attribute_type_combo.setCurrentIndex(0)

        bonus_type_text = str(payload.get("bonus_type", "固定值"))
        index_for_bonus = self.bonus_type_combo.findText(bonus_type_text)
        if index_for_bonus == -1:
            index_for_bonus = 0
        self.bonus_type_combo.setCurrentIndex(index_for_bonus)

        random_range_any = payload.get("random_range", [0.0, 0.0])
        if isinstance(random_range_any, Iterable):
            random_values: list[float] = []
            for raw_value in random_range_any:
                if isinstance(raw_value, (int, float)):
                    random_values.append(float(raw_value))
            if len(random_values) == 2:
                self.random_min_spin.setValue(random_values[0])
                self.random_max_spin.setValue(random_values[1])

        fixed_bonus_raw = payload.get("fixed_bonus", 0.0)
        if isinstance(fixed_bonus_raw, (int, float)):
            self.fixed_bonus_spin.setValue(float(fixed_bonus_raw))

        description_type_text = str(payload.get("description_type", "固定描述"))
        index_for_description = self.description_type_combo.findText(description_type_text)
        if index_for_description == -1:
            index_for_description = 0
        self.description_type_combo.setCurrentIndex(index_for_description)

        custom_description_text = str(payload.get("custom_description", ""))
        self.custom_description_edit.setPlainText(custom_description_text)

        self._refresh_preview_text()

    # ------------------------------------------------------------------ 保存逻辑

    def _refresh_preview_text(self) -> None:
        entry_name_text = self.entry_name_edit.text().strip()
        config_id_text = self.config_id_edit.text().strip()
        bonus_type_text = self.bonus_type_combo.currentText()

        if bonus_type_text == "固定值":
            preview_text = (
                f"{entry_name_text or '词条'}（配置ID {config_id_text or '-'}）："
                f"固定加成 {self.fixed_bonus_spin.value():.2f}"
            )
        else:
            preview_text = (
                f"{entry_name_text or '词条'}（配置ID {config_id_text or '-'}）："
                f"随机加成 [{self.random_min_spin.value():.2f}, {self.random_max_spin.value():.2f}]"
            )

        custom_description_text = self.custom_description_edit.toPlainText().strip()
        if custom_description_text:
            preview_text = custom_description_text

        self.preview_label.setText(preview_text)

    def _on_save_clicked(self) -> None:
        if self.current_payload is None or self.current_storage_id is None:
            return

        entry_name_text = self.entry_name_edit.text().strip()
        if not entry_name_text:
            dialog_utils.show_warning_dialog(self, "提示", "请输入词条名称")
            return

        config_id_text = self.config_id_edit.text().strip()
        if not config_id_text or not config_id_text.isdigit():
            dialog_utils.show_warning_dialog(self, "提示", "配置ID必须为只包含数字的非空字符串。")
            return

        self.current_payload["entry_name"] = entry_name_text
        self.current_payload["config_id"] = config_id_text
        self.current_payload["effect_timing"] = str(self.effect_timing_combo.currentText())
        self.current_payload["entry_type"] = str(self.entry_type_combo.currentText())
        self.current_payload["attribute_type"] = self.attribute_type_combo.currentText().strip()
        self.current_payload["bonus_type"] = str(self.bonus_type_combo.currentText())
        self.current_payload["random_range"] = [
            float(self.random_min_spin.value()),
            float(self.random_max_spin.value()),
        ]
        self.current_payload["fixed_bonus"] = float(self.fixed_bonus_spin.value())
        self.current_payload["description_type"] = str(self.description_type_combo.currentText())
        self.current_payload["custom_description"] = self.custom_description_edit.toPlainText().strip()

        self._refresh_preview_text()
        self.data_updated.emit()


class EquipmentTagManagementPanel(BaseEquipmentConfigPanel):
    """装备标签详情面板。"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="装备标签详情",
            description="编辑装备标签的名称、配置ID与说明文本。",
        )

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        form_container = QtWidgets.QWidget(scroll_area)
        form_layout = QtWidgets.QFormLayout(form_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        scroll_area.setWidget(form_container)
        self.body_layout.addWidget(scroll_area, 1)

        self.tag_id_label = QtWidgets.QLabel("-")
        form_layout.addRow("存储ID:", self.tag_id_label)

        self.tag_name_edit = QtWidgets.QLineEdit()
        form_layout.addRow("标签名称:", self.tag_name_edit)

        self.tag_config_id_edit = QtWidgets.QLineEdit()
        self.tag_config_id_edit.setPlaceholderText("纯数字配置ID，例如 1128267777")
        form_layout.addRow("配置ID:", self.tag_config_id_edit)

        self.tag_description_edit = QtWidgets.QPlainTextEdit()
        self.tag_description_edit.setMinimumHeight(80)
        self.tag_description_edit.setMaximumHeight(200)
        form_layout.addRow("标签说明:", self.tag_description_edit)

        reference_group = QtWidgets.QGroupBox("引用列表")
        reference_layout = QtWidgets.QVBoxLayout(reference_group)
        reference_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_reference_label = QtWidgets.QLabel("暂无引用的装备")
        self.tag_reference_label.setEnabled(False)
        self.tag_reference_label.setWordWrap(True)
        reference_layout.addWidget(self.tag_reference_label)
        form_layout.addRow(reference_group)

        button_row = QtWidgets.QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addStretch(1)
        self.tag_save_button = QtWidgets.QPushButton("保存标签")
        self.tag_save_button.setMinimumHeight(Sizes.BUTTON_HEIGHT)
        self.tag_save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.tag_save_button)
        self.body_layout.addLayout(button_row)

        self.setEnabled(False)

    def _clear_form(self) -> None:
        self.tag_id_label.setText("-")
        self.tag_name_edit.clear()
        self.tag_config_id_edit.clear()
        self.tag_description_edit.clear()
        self.tag_reference_label.setText("暂无引用的装备")

    def _load_from_payload(self, storage_id: str, payload: Dict[str, Any]) -> None:
        self.tag_id_label.setText(str(storage_id))
        self.tag_name_edit.setText(str(payload.get("tag_name", "")))
        self.tag_config_id_edit.setText(str(payload.get("config_id", "")))
        self.tag_description_edit.setPlainText(str(payload.get("description", "")))

    def _on_save_clicked(self) -> None:
        if self.current_payload is None or self.current_storage_id is None:
            return

        tag_name_text = self.tag_name_edit.text().strip()
        if not tag_name_text:
            dialog_utils.show_warning_dialog(self, "提示", "请输入标签名称")
            return

        config_id_text = self.tag_config_id_edit.text().strip()
        if not config_id_text or not config_id_text.isdigit():
            dialog_utils.show_warning_dialog(self, "提示", "配置ID必须为只包含数字的非空字符串。")
            return

        self.current_payload["tag_name"] = tag_name_text
        self.current_payload["config_id"] = config_id_text
        self.current_payload["description"] = self.tag_description_edit.toPlainText().strip()

        self.data_updated.emit()


class EquipmentTypeManagementPanel(BaseEquipmentConfigPanel):
    """装备类型详情面板。"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="装备类型详情",
            description="编辑装备类型的名称、配置ID与可装备槽位。",
        )

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        form_container = QtWidgets.QWidget(scroll_area)
        form_layout = QtWidgets.QFormLayout(form_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        scroll_area.setWidget(form_container)
        self.body_layout.addWidget(scroll_area, 1)

        self.type_id_label = QtWidgets.QLabel("-")
        form_layout.addRow("存储ID:", self.type_id_label)

        self.type_name_edit = QtWidgets.QLineEdit()
        form_layout.addRow("类型名称:", self.type_name_edit)

        self.type_config_id_edit = QtWidgets.QLineEdit()
        self.type_config_id_edit.setPlaceholderText("纯数字配置ID，例如 1124073473")
        form_layout.addRow("配置ID:", self.type_config_id_edit)

        self.type_description_edit = QtWidgets.QPlainTextEdit()
        self.type_description_edit.setMinimumHeight(60)
        self.type_description_edit.setMaximumHeight(200)
        form_layout.addRow("类型说明:", self.type_description_edit)

        self.allowed_slots_list = QtWidgets.QListWidget()
        self.allowed_slots_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        slot_options = ["weapon", "head", "body", "legs", "feet", "shield", "accessory"]
        for slot_name in slot_options:
            item = QtWidgets.QListWidgetItem(slot_name)
            self.allowed_slots_list.addItem(item)
        form_layout.addRow("可装备槽位:", self.allowed_slots_list)

        reference_group = QtWidgets.QGroupBox("引用列表")
        reference_layout = QtWidgets.QVBoxLayout(reference_group)
        reference_layout.setContentsMargins(0, 0, 0, 0)
        self.type_reference_label = QtWidgets.QLabel("暂无引用的装备")
        self.type_reference_label.setEnabled(False)
        self.type_reference_label.setWordWrap(True)
        reference_layout.addWidget(self.type_reference_label)
        form_layout.addRow(reference_group)

        button_row = QtWidgets.QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addStretch(1)
        self.type_save_button = QtWidgets.QPushButton("保存类型")
        self.type_save_button.setMinimumHeight(Sizes.BUTTON_HEIGHT)
        self.type_save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.type_save_button)
        self.body_layout.addLayout(button_row)

        self.setEnabled(False)

    def _clear_form(self) -> None:
        self.type_id_label.setText("-")
        self.type_name_edit.clear()
        self.type_config_id_edit.clear()
        self.type_description_edit.clear()
        for row_index in range(self.allowed_slots_list.count()):
            item = self.allowed_slots_list.item(row_index)
            if item is not None:
                item.setSelected(False)
        self.type_reference_label.setText("暂无引用的装备")

    def _load_from_payload(self, storage_id: str, payload: Dict[str, Any]) -> None:
        self.type_id_label.setText(str(storage_id))
        self.type_name_edit.setText(str(payload.get("type_name", "")))
        self.type_config_id_edit.setText(str(payload.get("config_id", "")))
        self.type_description_edit.setPlainText(str(payload.get("description", "")))

        allowed_slots_any = payload.get("allowed_slots", [])
        allowed_slots_set: set[str] = set()
        if isinstance(allowed_slots_any, Sequence):
            for slot_value in allowed_slots_any:
                if isinstance(slot_value, str) and slot_value.strip():
                    allowed_slots_set.add(slot_value.strip())

        for row_index in range(self.allowed_slots_list.count()):
            item = self.allowed_slots_list.item(row_index)
            if item is None:
                continue
            slot_name = item.text()
            item.setSelected(slot_name in allowed_slots_set)

    def _on_save_clicked(self) -> None:
        if self.current_payload is None or self.current_storage_id is None:
            return

        type_name_text = self.type_name_edit.text().strip()
        if not type_name_text:
            dialog_utils.show_warning_dialog(self, "提示", "请输入类型名称")
            return

        config_id_text = self.type_config_id_edit.text().strip()
        if not config_id_text or not config_id_text.isdigit():
            dialog_utils.show_warning_dialog(self, "提示", "配置ID必须为只包含数字的非空字符串。")
            return

        allowed_slots: list[str] = []
        for row_index in range(self.allowed_slots_list.count()):
            item = self.allowed_slots_list.item(row_index)
            if item is not None and item.isSelected():
                allowed_slots.append(item.text())

        self.current_payload["type_name"] = type_name_text
        self.current_payload["config_id"] = config_id_text
        self.current_payload["description"] = self.type_description_edit.toPlainText().strip()
        self.current_payload["allowed_slots"] = allowed_slots

        self.data_updated.emit()


__all__ = [
    "EquipmentEntryManagementPanel",
    "EquipmentTagManagementPanel",
    "EquipmentTypeManagementPanel",
]


