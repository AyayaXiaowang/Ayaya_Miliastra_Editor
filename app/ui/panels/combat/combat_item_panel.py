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

from datetime import datetime
from typing import Any, Dict, Optional, Union

from PyQt6 import QtCore, QtWidgets

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from app.ui.foundation.theme_manager import Colors
from app.ui.panels.combat.combat_item_edit_widget import CombatItemEditWidget
from app.ui.panels.combat.combat_preset_editor_structs import ItemEditorStruct
from app.ui.panels.panel_dict_utils import ensure_dict_field, ensure_nested_dict
from app.ui.panels.panel_scaffold import PanelScaffold


PresetPackage = Union[PackageView, GlobalResourceView]

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
        self.item_editor: ItemEditorStruct = ItemEditorStruct(basic={}, drop={}, interaction={})

        # 顶部状态徽章
        self._status_label = self.create_status_badge(
            "CombatItemStatusBadge",
            "未选中道具",
            background_color=Colors.INFO_BG,
            text_color=Colors.TEXT_PRIMARY,
        )

        self._edit_widget = CombatItemEditWidget(
            parent=self,
            resource_manager=self.resource_manager,
            package_index_manager=self.package_index_manager,
        )
        self._edit_widget.data_changed.connect(self._on_edit_data_changed)
        self.body_layout.addWidget(self._edit_widget, 1)
        self.setEnabled(False)

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
            self.item_editor = ItemEditorStruct(basic={}, drop={}, interaction={})
            self._edit_widget.set_context(
                package=None,
                item_id=None,
                item_data=None,
                item_editor=self.item_editor,
            )
            self.setEnabled(False)
            self._update_status_badge()
            return

        item_map = package.combat_presets.items
        item_data = item_map.get(item_id)
        if not isinstance(item_data, dict):
            self.current_item_data = None
            self.item_editor = ItemEditorStruct(basic={}, drop={}, interaction={})
            self._edit_widget.set_context(
                package=None,
                item_id=None,
                item_data=None,
                item_editor=self.item_editor,
            )
            self.setEnabled(False)
            self._update_status_badge()
            return

        self.current_item_data = item_data
        item_editor_raw = ensure_nested_dict(item_data, "metadata", "item_editor")
        basic_section = ensure_dict_field(item_editor_raw, "basic")
        drop_section = ensure_dict_field(item_editor_raw, "drop")
        interaction_section = ensure_dict_field(item_editor_raw, "interaction")

        self.item_editor = ItemEditorStruct(
            basic=basic_section,
            drop=drop_section,
            interaction=interaction_section,
        )

        self._edit_widget.set_context(
            package=self.current_package,
            item_id=self.current_item_id,
            item_data=self.current_item_data,
            item_editor=self.item_editor,
        )
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

    def _on_edit_data_changed(self) -> None:
        self._update_status_badge()
        self.data_changed.emit()


__all__ = ["CombatItemPanel"]


