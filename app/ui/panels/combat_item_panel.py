"""
道具详情面板（战斗预设-道具）。

该面板在战斗预设模式下作为主窗口右侧的一个标签页，用于编辑单个
战斗预设道具的基础与交互配置。设计上拆分为两个主标签页：

- “基础设置”：稀有度、堆叠上限、关联道具节点图、背包页签、简介与货币/掉落相关字段
- “交互设置”：销毁/交易/使用开关，以及冷却与冷却连带关系组等字段

数据约定：
- 道具基础字段（item_id/item_name/description/item_type/rarity/max_stack/use_effect/cooldown 等）
  直接写入 `ItemConfig` 对象对应的 JSON 字段；
- 本面板的扩展配置统一写入道具 JSON 的 `metadata.item_editor` 字段：
  - metadata.item_editor.basic:      基础与货币字段（inventory_tab/has_currency_value/currency_value 等）
  - metadata.item_editor.drop:       掉落表现字段（destroy_drop_form/drop_type/drop_appearance）
  - metadata.item_editor.interaction:交互行为字段（allow_destroy/allow_trade/allow_use 等）

面板本身只负责 UI 展示与字典读写，真正的持久化由外层 PackageController 负责，
通过 `data_changed` 信号触发立即保存。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from PyQt6 import QtCore, QtWidgets, QtGui

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from ui.dialogs.graph_selection_dialog import GraphSelectionDialog
from ui.foundation import dialog_utils
from ui.foundation.context_menu_builder import ContextMenuBuilder
from ui.foundation.theme_manager import Colors, Sizes
from ui.foundation.toggle_switch import ToggleSwitch
from ui.panels.panel_scaffold import PanelScaffold


PresetPackage = Union[PackageView, GlobalResourceView]


RARITY_DISPLAY_TO_KEY: Dict[str, str] = {
    "灰色": "common",
    "绿色": "uncommon",
    "蓝色": "rare",
    "紫色": "epic",
    "橙色": "legendary",
}
RARITY_KEY_TO_DISPLAY: Dict[str, str] = {value: key for key, value in RARITY_DISPLAY_TO_KEY.items()}


@dataclass
class _ItemEditorStruct:
    """内部道具编辑结构，分为基础/掉落/交互三个子段。"""

    basic: Dict[str, Any]
    drop: Dict[str, Any]
    interaction: Dict[str, Any]


class CombatItemPanel(PanelScaffold):
    """战斗预设-道具详情面板。"""

    data_changed = QtCore.pyqtSignal()

    def __init__(
        self,
        resource_manager: Optional[ResourceManager] = None,
        package_index_manager: Optional[PackageIndexManager] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            title="道具详情",
            description="在战斗预设模式下编辑单个道具的基础与交互设置。",
        )

        self.resource_manager: Optional[ResourceManager] = resource_manager
        self.package_index_manager: Optional[PackageIndexManager] = package_index_manager

        self.current_package: Optional[PresetPackage] = None
        self.current_item_id: Optional[str] = None
        self.current_item_data: Optional[Dict[str, Any]] = None
        self.item_editor: _ItemEditorStruct = _ItemEditorStruct(
            basic={},
            drop={},
            interaction={},
        )

        # 顶部状态徽章
        self._status_label = self.create_status_badge(
            "CombatItemStatusBadge",
            "未选中道具",
            background_color=Colors.INFO_BG,
            text_color=Colors.TEXT_PRIMARY,
        )

        # 顶部基础信息
        self.id_label: QtWidgets.QLabel
        self.name_edit: QtWidgets.QLineEdit
        self.item_type_combo: QtWidgets.QComboBox
        self.config_id_edit: QtWidgets.QLineEdit

        # 基础设置控件
        self.rarity_combo: QtWidgets.QComboBox
        self.stack_limit_spin: QtWidgets.QSpinBox
        self.graph_id_edit: QtWidgets.QLineEdit
        self.inventory_tab_combo: QtWidgets.QComboBox
        self.description_edit: QtWidgets.QTextEdit

        # 货币与掉落
        self.has_currency_switch: ToggleSwitch
        self.show_currency_switch: ToggleSwitch
        self.currency_value_spin: QtWidgets.QSpinBox
        self.destroy_drop_form_combo: QtWidgets.QComboBox
        self.drop_type_combo: QtWidgets.QComboBox
        self.drop_appearance_edit: QtWidgets.QLineEdit

        # 交互设置控件
        self.allow_destroy_switch: ToggleSwitch
        self.allow_trade_switch: ToggleSwitch
        self.allow_use_switch: ToggleSwitch
        self.batch_use_switch: ToggleSwitch
        self.auto_use_switch: ToggleSwitch
        self.cooldown_spin: QtWidgets.QDoubleSpinBox
        self.group_cooldown_spin: QtWidgets.QDoubleSpinBox
        self.cooldown_relation_list: QtWidgets.QListWidget

        self.tabs: QtWidgets.QTabWidget

        self._build_ui()
        self.setEnabled(False)

    # ------------------------------------------------------------------ UI 构建

    def _build_ui(self) -> None:
        self.tabs = QtWidgets.QTabWidget()
        self.body_layout.addWidget(self.tabs, 1)

        basic_page = QtWidgets.QWidget()
        interaction_page = QtWidgets.QWidget()
        self.tabs.addTab(basic_page, "基础设置")
        self.tabs.addTab(interaction_page, "交互设置")

        self._build_basic_tab(basic_page)
        self._build_interaction_tab(interaction_page)

    def _build_basic_tab(self, page: QtWidgets.QWidget) -> None:
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        layout.addWidget(scroll_area, 1)

        container = QtWidgets.QWidget()
        scroll_area.setWidget(container)

        main_layout = QtWidgets.QVBoxLayout(container)
        main_layout.setContentsMargins(
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
        )
        main_layout.setSpacing(Sizes.SPACING_MEDIUM)

        # 顶部基础信息：存储ID / 名称 / 类型
        basic_info_group = QtWidgets.QGroupBox("基础信息")
        basic_info_layout = QtWidgets.QFormLayout(basic_info_group)
        basic_info_layout.setSpacing(Sizes.SPACING_SMALL)

        self.id_label = QtWidgets.QLabel("-")
        basic_info_layout.addRow("存储ID:", self.id_label)

        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("例如：生命药水")
        self.name_edit.textChanged.connect(self._on_name_changed)
        basic_info_layout.addRow("道具名称:", self.name_edit)

        self.item_type_combo = QtWidgets.QComboBox()
        self.item_type_combo.addItems(
            [
                "消耗品",
                "装备",
                "材料",
                "任务道具",
            ]
        )
        self.item_type_combo.currentIndexChanged.connect(self._on_item_type_changed)
        basic_info_layout.addRow("道具类型:", self.item_type_combo)

        self.config_id_edit = QtWidgets.QLineEdit()
        self.config_id_edit.setPlaceholderText("仅作为数据用的配置ID，例如 1001（纯数字，可选）")
        self.config_id_edit.setValidator(QtGui.QIntValidator(0, 999999999))
        self.config_id_edit.editingFinished.connect(self._on_config_id_edited)
        basic_info_layout.addRow("配置ID(纯数字):", self.config_id_edit)

        main_layout.addWidget(basic_info_group)

        # 基础设置
        basic_group = QtWidgets.QGroupBox("基础设置")
        basic_layout = QtWidgets.QFormLayout(basic_group)
        basic_layout.setSpacing(Sizes.SPACING_SMALL)

        self.rarity_combo = QtWidgets.QComboBox()
        self.rarity_combo.addItems(["灰色", "绿色", "蓝色", "紫色", "橙色"])
        self.rarity_combo.currentIndexChanged.connect(self._on_rarity_changed)
        basic_layout.addRow("稀有度:", self.rarity_combo)

        self.stack_limit_spin = QtWidgets.QSpinBox()
        self.stack_limit_spin.setRange(1, 9999)
        self.stack_limit_spin.setValue(99)
        self.stack_limit_spin.valueChanged.connect(self._on_stack_limit_changed)
        basic_layout.addRow("堆叠上限:", self.stack_limit_spin)

        graph_row = QtWidgets.QWidget()
        graph_row_layout = QtWidgets.QHBoxLayout(graph_row)
        graph_row_layout.setContentsMargins(0, 0, 0, 0)
        graph_row_layout.setSpacing(Sizes.SPACING_SMALL)

        self.graph_id_edit = QtWidgets.QLineEdit()
        self.graph_id_edit.setPlaceholderText("未关联，道具使用效果可绑定节点图ID")
        self.graph_id_edit.textChanged.connect(self._on_graph_id_text_changed)
        graph_row_layout.addWidget(self.graph_id_edit, 1)

        graph_select_btn = QtWidgets.QPushButton("点击选择")
        graph_select_btn.clicked.connect(self._on_select_graph_clicked)
        graph_row_layout.addWidget(graph_select_btn)

        basic_layout.addRow("关联道具节点图:", graph_row)

        self.inventory_tab_combo = QtWidgets.QComboBox()
        self.inventory_tab_combo.setEditable(True)
        self.inventory_tab_combo.addItems(["材料", "消耗品", "装备", "任务", "其他"])
        self.inventory_tab_combo.currentIndexChanged.connect(self._on_inventory_tab_changed)
        self.inventory_tab_combo.lineEdit().editingFinished.connect(self._on_inventory_tab_edited)
        basic_layout.addRow("背包内归属页签:", self.inventory_tab_combo)

        main_layout.addWidget(basic_group)

        # 简介
        desc_group = QtWidgets.QGroupBox("简介")
        desc_layout = QtWidgets.QVBoxLayout(desc_group)
        desc_layout.setContentsMargins(0, 0, 0, 0)
        desc_layout.setSpacing(Sizes.SPACING_SMALL)

        self.description_edit = QtWidgets.QTextEdit()
        self.description_edit.setMinimumHeight(80)
        self.description_edit.setMaximumHeight(180)
        self.description_edit.setPlaceholderText("描述该道具的用途、获得方式或设计思路...")
        self.description_edit.textChanged.connect(self._on_description_changed)
        desc_layout.addWidget(self.description_edit)

        main_layout.addWidget(desc_group)

        # 货币与掉落设置
        currency_group = QtWidgets.QGroupBox("货币与掉落设置")
        currency_layout = QtWidgets.QFormLayout(currency_group)
        currency_layout.setSpacing(Sizes.SPACING_SMALL)

        self.has_currency_switch = ToggleSwitch()
        self.has_currency_switch.stateChanged.connect(self._on_has_currency_changed)
        currency_layout.addRow("是否有货币价值:", self.has_currency_switch)

        self.show_currency_switch = ToggleSwitch()
        self.show_currency_switch.stateChanged.connect(self._on_show_currency_changed)
        currency_layout.addRow("显示货币价值:", self.show_currency_switch)

        self.currency_value_spin = QtWidgets.QSpinBox()
        self.currency_value_spin.setRange(0, 999999999)
        self.currency_value_spin.valueChanged.connect(self._on_currency_value_changed)
        currency_layout.addRow("货币价值:", self.currency_value_spin)

        self.destroy_drop_form_combo = QtWidgets.QComboBox()
        self.destroy_drop_form_combo.addItems(
            [
                "应用道具掉落规则",
                "掉落",
                "销毁",
                "保留",
            ]
        )
        self.destroy_drop_form_combo.currentIndexChanged.connect(self._on_destroy_drop_form_changed)
        currency_layout.addRow("销毁时掉落形态:", self.destroy_drop_form_combo)

        self.drop_type_combo = QtWidgets.QComboBox()
        self.drop_type_combo.addItems(["全员一份", "每人一份"])
        self.drop_type_combo.currentIndexChanged.connect(self._on_drop_type_changed)
        currency_layout.addRow("战利品掉落形式:", self.drop_type_combo)

        drop_row = QtWidgets.QWidget()
        drop_row_layout = QtWidgets.QHBoxLayout(drop_row)
        drop_row_layout.setContentsMargins(0, 0, 0, 0)
        drop_row_layout.setSpacing(Sizes.SPACING_SMALL)

        self.drop_appearance_edit = QtWidgets.QLineEdit()
        self.drop_appearance_edit.setPlaceholderText("输入或选择对应掉落物外形ID")
        self.drop_appearance_edit.textChanged.connect(self._on_drop_appearance_changed)
        drop_row_layout.addWidget(self.drop_appearance_edit, 1)

        drop_config_btn = QtWidgets.QPushButton("点击配置掉落物")
        drop_config_btn.clicked.connect(self._on_configure_drop_clicked)
        drop_row_layout.addWidget(drop_config_btn)

        currency_layout.addRow("对应掉落物外形:", drop_row)

        main_layout.addWidget(currency_group)
        main_layout.addStretch(1)

    def _build_interaction_tab(self, page: QtWidgets.QWidget) -> None:
        main_layout = QtWidgets.QVBoxLayout(page)
        main_layout.setContentsMargins(
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
        )
        main_layout.setSpacing(Sizes.SPACING_MEDIUM)

        interaction_group = QtWidgets.QGroupBox("交互设置")
        interaction_layout = QtWidgets.QFormLayout(interaction_group)
        interaction_layout.setSpacing(Sizes.SPACING_SMALL)

        self.allow_destroy_switch = ToggleSwitch()
        self.allow_destroy_switch.stateChanged.connect(self._on_allow_destroy_changed)
        interaction_layout.addRow("允许销毁:", self.allow_destroy_switch)

        self.allow_trade_switch = ToggleSwitch()
        self.allow_trade_switch.stateChanged.connect(self._on_allow_trade_changed)
        interaction_layout.addRow("允许交易:", self.allow_trade_switch)

        self.allow_use_switch = ToggleSwitch()
        self.allow_use_switch.stateChanged.connect(self._on_allow_use_changed)
        interaction_layout.addRow("允许使用:", self.allow_use_switch)

        use_group = QtWidgets.QGroupBox("使用行为")
        use_layout = QtWidgets.QFormLayout(use_group)
        use_layout.setSpacing(Sizes.SPACING_SMALL)

        self.batch_use_switch = ToggleSwitch()
        self.batch_use_switch.stateChanged.connect(self._on_batch_use_changed)
        use_layout.addRow("是否可批量使用:", self.batch_use_switch)

        self.auto_use_switch = ToggleSwitch()
        self.auto_use_switch.stateChanged.connect(self._on_auto_use_changed)
        use_layout.addRow("进包后自动使用:", self.auto_use_switch)

        self.cooldown_spin = QtWidgets.QDoubleSpinBox()
        self.cooldown_spin.setRange(0.0, 999999.0)
        self.cooldown_spin.setDecimals(2)
        self.cooldown_spin.setSingleStep(0.1)
        self.cooldown_spin.setSuffix(" 秒")
        self.cooldown_spin.valueChanged.connect(self._on_cooldown_changed)
        use_layout.addRow("冷却时间(s):", self.cooldown_spin)

        self.group_cooldown_spin = QtWidgets.QDoubleSpinBox()
        self.group_cooldown_spin.setRange(0.0, 999999.0)
        self.group_cooldown_spin.setDecimals(2)
        self.group_cooldown_spin.setSingleStep(0.1)
        self.group_cooldown_spin.setSuffix(" 秒")
        self.group_cooldown_spin.valueChanged.connect(self._on_group_cooldown_changed)
        use_layout.addRow("关系组冷却时间(s):", self.group_cooldown_spin)

        relation_container = QtWidgets.QWidget()
        relation_layout = QtWidgets.QVBoxLayout(relation_container)
        relation_layout.setContentsMargins(0, 0, 0, 0)
        relation_layout.setSpacing(Sizes.SPACING_SMALL)

        self.cooldown_relation_list = QtWidgets.QListWidget()
        self.cooldown_relation_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.cooldown_relation_list.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.cooldown_relation_list.customContextMenuRequested.connect(
            self._on_cooldown_relation_context_menu
        )
        relation_layout.addWidget(self.cooldown_relation_list, 1)

        relation_button_row = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("添加道具")
        add_btn.clicked.connect(self._on_add_cooldown_relation)
        remove_btn = QtWidgets.QPushButton("移除选中")
        remove_btn.clicked.connect(self._on_remove_cooldown_relation)
        relation_button_row.addWidget(add_btn)
        relation_button_row.addWidget(remove_btn)
        relation_button_row.addStretch(1)
        relation_layout.addLayout(relation_button_row)

        use_layout.addRow("冷却连带关系组:", relation_container)

        interaction_layout.addRow(use_group)
        main_layout.addWidget(interaction_group)
        main_layout.addStretch(1)

        self._sync_interaction_controls_enabled_state()

    # ------------------------------------------------------------------ 上下文管理

    def set_context(
        self,
        package: Optional[PresetPackage],
        item_id: Optional[str],
    ) -> None:
        """设置当前道具上下文并加载字段。"""
        self.current_package = package
        self.current_item_id = item_id

        if not package or not item_id:
            self.current_item_data = None
            self.item_editor = _ItemEditorStruct(
                basic={},
                drop={},
                interaction={},
            )
            self._clear_ui()
            self.setEnabled(False)
            self._update_status_badge()
            return

        item_map = package.combat_presets.items
        item_data = item_map.get(item_id)
        if not isinstance(item_data, dict):
            self.current_item_data = None
            self.item_editor = _ItemEditorStruct(
                basic={},
                drop={},
                interaction={},
            )
            self._clear_ui()
            self.setEnabled(False)
            self._update_status_badge()
            return

        self.current_item_data = item_data

        metadata = item_data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            item_data["metadata"] = metadata

        item_editor_raw = metadata.get("item_editor")
        if not isinstance(item_editor_raw, dict):
            item_editor_raw = {}
            metadata["item_editor"] = item_editor_raw

        basic_section = item_editor_raw.get("basic")
        if not isinstance(basic_section, dict):
            basic_section = {}
            item_editor_raw["basic"] = basic_section

        drop_section = item_editor_raw.get("drop")
        if not isinstance(drop_section, dict):
            drop_section = {}
            item_editor_raw["drop"] = drop_section

        interaction_section = item_editor_raw.get("interaction")
        if not isinstance(interaction_section, dict):
            interaction_section = {}
            item_editor_raw["interaction"] = interaction_section

        self.item_editor = _ItemEditorStruct(
            basic=basic_section,
            drop=drop_section,
            interaction=interaction_section,
        )

        self._load_fields()
        self._update_status_badge()
        self.setEnabled(True)

    def _update_status_badge(self) -> None:
        if not self._status_label:
            return
        if not self.current_item_id or not self.current_item_data:
            self._status_label.setText("未选中道具")
            self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.TEXT_PRIMARY)
            return
        name_value = str(self.current_item_data.get("item_name", "")).strip()
        display_name = name_value or self.current_item_id
        self._status_label.setText(f"道具 · {display_name}")
        self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.PRIMARY)

    # ------------------------------------------------------------------ 加载与重置

    def _clear_ui(self) -> None:
        self.id_label.setText("-")

        self.name_edit.blockSignals(True)
        self.name_edit.clear()
        self.name_edit.blockSignals(False)

        self.item_type_combo.blockSignals(True)
        self.item_type_combo.setCurrentIndex(0)
        self.item_type_combo.blockSignals(False)

        self.config_id_edit.blockSignals(True)
        self.config_id_edit.clear()
        self.config_id_edit.blockSignals(False)

        self.rarity_combo.blockSignals(True)
        self.rarity_combo.setCurrentIndex(0)
        self.rarity_combo.blockSignals(False)

        self.stack_limit_spin.blockSignals(True)
        self.stack_limit_spin.setValue(99)
        self.stack_limit_spin.blockSignals(False)

        self.graph_id_edit.blockSignals(True)
        self.graph_id_edit.clear()
        self.graph_id_edit.blockSignals(False)

        self.inventory_tab_combo.blockSignals(True)
        self.inventory_tab_combo.setCurrentIndex(0)
        self.inventory_tab_combo.blockSignals(False)

        self.description_edit.blockSignals(True)
        self.description_edit.clear()
        self.description_edit.blockSignals(False)

        for switch_widget in (
            self.has_currency_switch,
            self.show_currency_switch,
            self.allow_destroy_switch,
            self.allow_trade_switch,
            self.allow_use_switch,
            self.batch_use_switch,
            self.auto_use_switch,
        ):
            switch_widget.blockSignals(True)
            switch_widget.setChecked(False)
            switch_widget.blockSignals(False)

        self.currency_value_spin.blockSignals(True)
        self.currency_value_spin.setValue(0)
        self.currency_value_spin.blockSignals(False)

        self.destroy_drop_form_combo.blockSignals(True)
        self.destroy_drop_form_combo.setCurrentIndex(0)
        self.destroy_drop_form_combo.blockSignals(False)

        self.drop_type_combo.blockSignals(True)
        self.drop_type_combo.setCurrentIndex(0)
        self.drop_type_combo.blockSignals(False)

        self.drop_appearance_edit.blockSignals(True)
        self.drop_appearance_edit.clear()
        self.drop_appearance_edit.blockSignals(False)

        self.cooldown_spin.blockSignals(True)
        self.cooldown_spin.setValue(0.0)
        self.cooldown_spin.blockSignals(False)

        self.group_cooldown_spin.blockSignals(True)
        self.group_cooldown_spin.setValue(0.0)
        self.group_cooldown_spin.blockSignals(False)

        self.cooldown_relation_list.clear()
        self._sync_interaction_controls_enabled_state()

    def _load_fields(self) -> None:
        if not self.current_item_data:
            self._clear_ui()
            return

        self.id_label.setText(str(self.current_item_id or "-"))

        name_value = str(self.current_item_data.get("item_name", "")).strip()
        self.name_edit.blockSignals(True)
        self.name_edit.setText(name_value)
        self.name_edit.blockSignals(False)

        item_type_text = str(self.current_item_data.get("item_type", "consumable"))
        item_type_map = {
            "consumable": "消耗品",
            "equipment": "装备",
            "material": "材料",
            "quest": "任务道具",
        }
        display_type = item_type_map.get(item_type_text, "消耗品")
        index = self.item_type_combo.findText(display_type)
        if index < 0:
            index = 0
        self.item_type_combo.blockSignals(True)
        self.item_type_combo.setCurrentIndex(index)
        self.item_type_combo.blockSignals(False)

        config_id_text = str(self.current_item_data.get("config_id", "")).strip()
        self.config_id_edit.blockSignals(True)
        self.config_id_edit.setText(config_id_text)
        self.config_id_edit.blockSignals(False)

        rarity_key = str(self.current_item_data.get("rarity", "common"))
        rarity_display = RARITY_KEY_TO_DISPLAY.get(rarity_key, "灰色")
        rarity_index = self.rarity_combo.findText(rarity_display)
        if rarity_index < 0:
            rarity_index = 0
        self.rarity_combo.blockSignals(True)
        self.rarity_combo.setCurrentIndex(rarity_index)
        self.rarity_combo.blockSignals(False)

        max_stack_value_any = self.current_item_data.get("max_stack", 99)
        max_stack_value = int(max_stack_value_any if isinstance(max_stack_value_any, int) else 99)
        self.stack_limit_spin.blockSignals(True)
        self.stack_limit_spin.setValue(max_stack_value)
        self.stack_limit_spin.blockSignals(False)

        use_effect_text = str(self.current_item_data.get("use_effect", "")).strip()
        self.graph_id_edit.blockSignals(True)
        self.graph_id_edit.setText(use_effect_text)
        self.graph_id_edit.blockSignals(False)

        basic_section = self.item_editor.basic
        inventory_tab_text = str(basic_section.get("inventory_tab", "材料")).strip()
        if not inventory_tab_text:
            inventory_tab_text = "材料"
        if self.inventory_tab_combo.findText(inventory_tab_text) == -1:
            self.inventory_tab_combo.addItem(inventory_tab_text)
        index = self.inventory_tab_combo.findText(inventory_tab_text)
        if index < 0:
            index = 0
        self.inventory_tab_combo.blockSignals(True)
        self.inventory_tab_combo.setCurrentIndex(index)
        self.inventory_tab_combo.blockSignals(False)

        description_text = str(self.current_item_data.get("description", "")).strip()
        self.description_edit.blockSignals(True)
        self.description_edit.setPlainText(description_text)
        self.description_edit.blockSignals(False)

        has_currency = bool(basic_section.get("has_currency_value", False))
        self.has_currency_switch.blockSignals(True)
        self.has_currency_switch.setChecked(has_currency)
        self.has_currency_switch.blockSignals(False)

        show_currency = bool(basic_section.get("show_currency_value", False))
        self.show_currency_switch.blockSignals(True)
        self.show_currency_switch.setChecked(show_currency)
        self.show_currency_switch.blockSignals(False)

        currency_value_any = basic_section.get("currency_value", 0)
        currency_value = int(currency_value_any if isinstance(currency_value_any, int) else 0)
        self.currency_value_spin.blockSignals(True)
        self.currency_value_spin.setValue(currency_value)
        self.currency_value_spin.blockSignals(False)

        drop_section = self.item_editor.drop
        destroy_drop_form = str(
            drop_section.get("destroy_drop_form", "应用道具掉落规则")
        ).strip()
        if not destroy_drop_form:
            destroy_drop_form = "应用道具掉落规则"
        destroy_index = self.destroy_drop_form_combo.findText(destroy_drop_form)
        if destroy_index < 0:
            destroy_index = 0
        self.destroy_drop_form_combo.blockSignals(True)
        self.destroy_drop_form_combo.setCurrentIndex(destroy_index)
        self.destroy_drop_form_combo.blockSignals(False)

        drop_type_text = str(drop_section.get("drop_type", "全员一份")).strip()
        if not drop_type_text:
            drop_type_text = "全员一份"
        drop_type_index = self.drop_type_combo.findText(drop_type_text)
        if drop_type_index < 0:
            drop_type_index = 0
        self.drop_type_combo.blockSignals(True)
        self.drop_type_combo.setCurrentIndex(drop_type_index)
        self.drop_type_combo.blockSignals(False)

        drop_appearance = str(drop_section.get("drop_appearance", "")).strip()
        self.drop_appearance_edit.blockSignals(True)
        self.drop_appearance_edit.setText(drop_appearance)
        self.drop_appearance_edit.blockSignals(False)

        interaction_section = self.item_editor.interaction
        allow_destroy = bool(interaction_section.get("allow_destroy", True))
        self.allow_destroy_switch.blockSignals(True)
        self.allow_destroy_switch.setChecked(allow_destroy)
        self.allow_destroy_switch.blockSignals(False)

        allow_trade = bool(interaction_section.get("allow_trade", True))
        self.allow_trade_switch.blockSignals(True)
        self.allow_trade_switch.setChecked(allow_trade)
        self.allow_trade_switch.blockSignals(False)

        allow_use = bool(interaction_section.get("allow_use", False))
        self.allow_use_switch.blockSignals(True)
        self.allow_use_switch.setChecked(allow_use)
        self.allow_use_switch.blockSignals(False)

        batch_use = bool(interaction_section.get("batch_use_allowed", False))
        self.batch_use_switch.blockSignals(True)
        self.batch_use_switch.setChecked(batch_use)
        self.batch_use_switch.blockSignals(False)

        auto_use = bool(interaction_section.get("auto_use_on_acquire", False))
        self.auto_use_switch.blockSignals(True)
        self.auto_use_switch.setChecked(auto_use)
        self.auto_use_switch.blockSignals(False)

        cooldown_value = float(
            interaction_section.get(
                "cooldown_time",
                self.current_item_data.get("cooldown", 0.0),
            )
        )
        self.cooldown_spin.blockSignals(True)
        self.cooldown_spin.setValue(cooldown_value)
        self.cooldown_spin.blockSignals(False)

        group_cooldown_value = float(interaction_section.get("group_cooldown_time", 0.0))
        self.group_cooldown_spin.blockSignals(True)
        self.group_cooldown_spin.setValue(group_cooldown_value)
        self.group_cooldown_spin.blockSignals(False)

        self._reload_cooldown_relation_list()
        self._sync_interaction_controls_enabled_state()

    # ------------------------------------------------------------------ 工具

    def _mark_item_modified(self) -> None:
        if not self.current_item_data:
            return
        self.current_item_data["last_modified"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def _sync_interaction_controls_enabled_state(self) -> None:
        allow_use = self.allow_use_switch.isChecked()
        self.batch_use_switch.setEnabled(allow_use)
        self.auto_use_switch.setEnabled(allow_use)
        self.cooldown_spin.setEnabled(allow_use)
        self.group_cooldown_spin.setEnabled(allow_use)
        self.cooldown_relation_list.setEnabled(allow_use)

    def _reload_cooldown_relation_list(self) -> None:
        self.cooldown_relation_list.clear()
        values_any = self.item_editor.interaction.get("cooldown_relation_group", [])
        if not isinstance(values_any, list):
            return
        for value in values_any:
            text = str(value).strip()
            if not text:
                continue
            item = QtWidgets.QListWidgetItem(text)
            self.cooldown_relation_list.addItem(item)

    # ------------------------------------------------------------------ 槽函数：基础信息

    def _on_name_changed(self, text: str) -> None:
        if not self.current_item_data:
            return
        self.current_item_data["item_name"] = text.strip()
        self._mark_item_modified()
        self._update_status_badge()
        self.data_changed.emit()

    def _on_item_type_changed(self, index: int) -> None:
        del index
        if not self.current_item_data:
            return
        display = self.item_type_combo.currentText()
        reverse_map = {
            "消耗品": "consumable",
            "装备": "equipment",
            "材料": "material",
            "任务道具": "quest",
        }
        self.current_item_data["item_type"] = reverse_map.get(display, "consumable")
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_config_id_edited(self) -> None:
        if not self.current_item_data:
            return
        text = self.config_id_edit.text().strip()
        if text:
            self.current_item_data["config_id"] = text
        else:
            self.current_item_data.pop("config_id", None)
        self._mark_item_modified()
        self.data_changed.emit()

    # ------------------------------------------------------------------ 槽函数：基础设置

    def _on_rarity_changed(self, index: int) -> None:
        del index
        if not self.current_item_data:
            return
        display = self.rarity_combo.currentText()
        rarity_key = RARITY_DISPLAY_TO_KEY.get(display, "common")
        self.current_item_data["rarity"] = rarity_key
        self.item_editor.basic["rarity_display"] = display
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_stack_limit_changed(self, value: int) -> None:
        if not self.current_item_data:
            return
        self.current_item_data["max_stack"] = int(value)
        self.item_editor.basic["stack_limit"] = int(value)
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_graph_id_text_changed(self, text: str) -> None:
        if not self.current_item_data:
            return
        self.current_item_data["use_effect"] = text.strip()
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_select_graph_clicked(self) -> None:
        if not self.resource_manager or not self.package_index_manager:
            dialog_utils.show_warning_dialog(self, "未配置", "当前环境未提供节点图库资源管理器。")
            return
        dialog = GraphSelectionDialog(
            resource_manager=self.resource_manager,
            package_index_manager=self.package_index_manager,
            parent=self,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        graph_id = dialog.get_selected_graph_id()
        if not graph_id:
            return
        self.graph_id_edit.setText(graph_id)
        self._on_graph_id_text_changed(graph_id)

    def _on_inventory_tab_changed(self, index: int) -> None:
        del index
        self._on_inventory_tab_edited()

    def _on_inventory_tab_edited(self) -> None:
        if not self.current_item_data:
            return
        text = self.inventory_tab_combo.currentText().strip()
        if not text:
            text = "材料"
        self.item_editor.basic["inventory_tab"] = text
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_description_changed(self) -> None:
        if not self.current_item_data:
            return
        self.current_item_data["description"] = self.description_edit.toPlainText().strip()
        self._mark_item_modified()
        self.data_changed.emit()

    # ------------------------------------------------------------------ 槽函数：货币与掉落

    def _on_has_currency_changed(self, state: int) -> None:
        if not self.current_item_data:
            return
        has_currency = state == QtCore.Qt.CheckState.Checked.value
        self.item_editor.basic["has_currency_value"] = has_currency
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_show_currency_changed(self, state: int) -> None:
        if not self.current_item_data:
            return
        show_currency = state == QtCore.Qt.CheckState.Checked.value
        self.item_editor.basic["show_currency_value"] = show_currency
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_currency_value_changed(self, value: int) -> None:
        if not self.current_item_data:
            return
        self.item_editor.basic["currency_value"] = int(value)
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_destroy_drop_form_changed(self, index: int) -> None:
        del index
        if not self.current_item_data:
            return
        text = self.destroy_drop_form_combo.currentText().strip()
        self.item_editor.drop["destroy_drop_form"] = text
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_drop_type_changed(self, index: int) -> None:
        del index
        if not self.current_item_data:
            return
        text = self.drop_type_combo.currentText().strip()
        self.item_editor.drop["drop_type"] = text
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_drop_appearance_changed(self, text: str) -> None:
        if not self.current_item_data:
            return
        self.item_editor.drop["drop_appearance"] = text.strip()
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_configure_drop_clicked(self) -> None:
        dialog_utils.show_info_dialog(
            self,
            "暂未实现",
            "掉落物外形的详细配置暂未接入本面板，请在相关管理页面中编辑。",
        )

    # ------------------------------------------------------------------ 槽函数：交互设置

    def _on_allow_destroy_changed(self, state: int) -> None:
        if not self.current_item_data:
            return
        self.item_editor.interaction["allow_destroy"] = (
            state == QtCore.Qt.CheckState.Checked.value
        )
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_allow_trade_changed(self, state: int) -> None:
        if not self.current_item_data:
            return
        self.item_editor.interaction["allow_trade"] = (
            state == QtCore.Qt.CheckState.Checked.value
        )
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_allow_use_changed(self, state: int) -> None:
        if not self.current_item_data:
            return
        allow_use = state == QtCore.Qt.CheckState.Checked.value
        self.item_editor.interaction["allow_use"] = allow_use
        self._sync_interaction_controls_enabled_state()
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_batch_use_changed(self, state: int) -> None:
        if not self.current_item_data:
            return
        self.item_editor.interaction["batch_use_allowed"] = (
            state == QtCore.Qt.CheckState.Checked.value
        )
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_auto_use_changed(self, state: int) -> None:
        if not self.current_item_data:
            return
        self.item_editor.interaction["auto_use_on_acquire"] = (
            state == QtCore.Qt.CheckState.Checked.value
        )
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_cooldown_changed(self, value: float) -> None:
        if not self.current_item_data:
            return
        cooldown_value = float(value)
        self.item_editor.interaction["cooldown_time"] = cooldown_value
        self.current_item_data["cooldown"] = cooldown_value
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_group_cooldown_changed(self, value: float) -> None:
        if not self.current_item_data:
            return
        self.item_editor.interaction["group_cooldown_time"] = float(value)
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_add_cooldown_relation(self) -> None:
        if not self.current_item_data:
            return
        text = dialog_utils.prompt_text(
            self,
            "添加道具",
            "请输入需要与当前道具共享冷却的道具ID或配置名：",
            "",
        )
        if not text:
            return
        value = text.strip()
        if not value:
            return
        existing_any = self.item_editor.interaction.get("cooldown_relation_group", [])
        if isinstance(existing_any, list):
            relation_list: List[str] = [str(item) for item in existing_any]
        else:
            relation_list = []
        if value in relation_list:
            return
        relation_list.append(value)
        self.item_editor.interaction["cooldown_relation_group"] = relation_list
        self._reload_cooldown_relation_list()
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_remove_cooldown_relation(self) -> None:
        if not self.current_item_data:
            return
        current_item = self.cooldown_relation_list.currentItem()
        if current_item is None:
            return
        value = current_item.text().strip()
        existing_any = self.item_editor.interaction.get("cooldown_relation_group", [])
        if not isinstance(existing_any, list):
            return
        relation_list: List[str] = [str(item) for item in existing_any if str(item).strip()]
        if value not in relation_list:
            return
        relation_list = [item for item in relation_list if item != value]
        self.item_editor.interaction["cooldown_relation_group"] = relation_list
        self._reload_cooldown_relation_list()
        self._mark_item_modified()
        self.data_changed.emit()

    def _on_cooldown_relation_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.cooldown_relation_list.itemAt(pos)
        if item is None:
            return
        builder = ContextMenuBuilder(self.cooldown_relation_list)
        builder.add_action("删除当前行", self._on_remove_cooldown_relation)
        builder.exec_for(self.cooldown_relation_list, pos)


__all__ = ["CombatItemPanel"]


