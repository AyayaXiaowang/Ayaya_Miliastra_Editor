"""技能详情面板（战斗预设-技能）。

该面板在战斗预设模式下作为主窗口右侧的一个标签页，用于编辑单个“技能”预设的
详细配置字段，对应设计文档中的“技能页面”（基础设置 / 连段配置 / 数值配置 /
生命周期管理等分组）。

数据结构约定：
- 技能资源的基础字段（skill_id/skill_name/description/...）仍由战斗预设模型管理；
- 本面板的扩展配置写入技能 JSON 的 `metadata.skill_editor` 字段：
  - metadata.skill_editor.basic:   基础设置（启用坠崖保护、是否可在空中释放、技能备注）
  - metadata.skill_editor.combo:   连段配置（是否开启蓄力分支、蓄力公共前摇）
  - metadata.skill_editor.numeric: 数值配置（冷却/次数/消耗/索敌范围等）
  - metadata.skill_editor.lifecycle: 生命周期管理（次数上限与销毁策略）

面板本身只负责 UI 展示与字典读写，真正的持久化由外层 PackageController 负责，
通过 `data_changed` 信号触发立即保存。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Union

from PyQt6 import QtCore, QtWidgets

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from ui.foundation.theme_manager import Colors, Sizes
from ui.foundation.toggle_switch import ToggleSwitch
from ui.panels.combat_player_panel_sections import _GraphBindingContext
from ui.panels.panel_scaffold import PanelScaffold
from ui.panels.template_instance.graphs_tab import GraphsTab
from ui.panels.template_instance_service import TemplateInstanceService


PresetPackage = Union[PackageView, GlobalResourceView]
SkillGraphsContext = _GraphBindingContext


@dataclass
class _SkillEditorStruct:
    """内部技能编辑结构，包裹四个分组字典，便于类型约束与后续扩展。"""

    basic: Dict[str, Any]
    combo: Dict[str, Any]
    numeric: Dict[str, Any]
    lifecycle: Dict[str, Any]


class CombatSkillPanel(PanelScaffold):
    """技能详情面板。

    - 左上方状态徽章展示当前技能名；
    - 主体采用单页 + 分组（基础设置/连段配置/数值配置/生命周期管理）布局；
    - 所有字段变更会更新技能 JSON 的 metadata.skill_editor 段并通过 data_changed
      信号通知外层立即持久化。
    """

    data_changed = QtCore.pyqtSignal()
    # 节点图被双击或通过按钮请求打开时发射，由主窗口负责实际打开图编辑器
    graph_selected = QtCore.pyqtSignal(str, dict)

    def __init__(
        self,
        resource_manager: Optional[ResourceManager] = None,
        package_index_manager: Optional[PackageIndexManager] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            title="技能详情",
            description="在战斗预设模式下编辑单个技能的基础设置、连段与数值配置。",
        )

        self.resource_manager: Optional[ResourceManager] = resource_manager
        self.package_index_manager: Optional[PackageIndexManager] = package_index_manager

        self.current_package: Optional[PresetPackage] = None
        self.current_skill_id: Optional[str] = None
        self.current_skill_data: Optional[Dict[str, Any]] = None
        self.skill_editor: _SkillEditorStruct = _SkillEditorStruct(
            basic={},
            combo={},
            numeric={},
            lifecycle={},
        )

        # 节点图上下文与服务（复用模板/实例面板中的 GraphsTab 能力）
        self._graph_service = TemplateInstanceService()
        self.skill_graphs_context: Optional[SkillGraphsContext] = None
        self.skill_graphs_tab: Optional[GraphsTab] = None

        # 主标签页：技能编辑 / 节点图
        self.main_tabs: QtWidgets.QTabWidget

        # 顶部状态徽章
        self._status_label = self.create_status_badge(
            "CombatSkillStatusBadge",
            "未选中技能",
            background_color=Colors.INFO_BG,
            text_color=Colors.TEXT_PRIMARY,
        )

        # --- 顶部基础信息控件 ---
        self.id_label: QtWidgets.QLabel
        self.name_edit: QtWidgets.QLineEdit
        self.skill_type_combo: QtWidgets.QComboBox

        # --- 基础设置 ---
        self.enable_cliff_protection_switch: ToggleSwitch
        self.can_use_in_air_switch: ToggleSwitch
        self.skill_note_edit: QtWidgets.QTextEdit

        # --- 连段配置 ---
        self.enable_charge_branch_switch: ToggleSwitch
        self.shared_charge_precast_switch: ToggleSwitch

        # --- 数值配置 ---
        self.has_cooldown_switch: ToggleSwitch
        self.cooldown_spin: QtWidgets.QDoubleSpinBox

        self.has_usage_limit_switch: ToggleSwitch
        self.usage_count_spin: QtWidgets.QSpinBox

        self.has_cost_switch: ToggleSwitch
        self.cost_type_edit: QtWidgets.QLineEdit
        self.cost_amount_spin: QtWidgets.QDoubleSpinBox

        self.target_range_type_combo: QtWidgets.QComboBox
        self.target_radius_spin: QtWidgets.QDoubleSpinBox
        self.target_height_spin: QtWidgets.QDoubleSpinBox

        # --- 生命周期管理 ---
        self.destroy_on_limit_switch: ToggleSwitch
        self.max_usage_count_spin: QtWidgets.QSpinBox

        self._build_ui()
        self.setEnabled(False)

    # ------------------------------------------------------------------ UI 构建

    def _build_ui(self) -> None:
        """搭建“技能编辑 / 节点图”两个主标签页。"""
        self.main_tabs = QtWidgets.QTabWidget()
        self.body_layout.addWidget(self.main_tabs, 1)

        edit_page = QtWidgets.QWidget()
        graphs_page = QtWidgets.QWidget()

        self.main_tabs.addTab(edit_page, "技能编辑")
        self.main_tabs.addTab(graphs_page, "节点图")

        self._build_edit_tab(edit_page)
        self._build_graphs_tab(graphs_page)

    def _build_edit_tab(self, page: QtWidgets.QWidget) -> None:
        """构建“技能编辑”标签页（原单页表单）。"""
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        page_layout = QtWidgets.QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_layout.addWidget(scroll_area, 1)

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

        # --- 基础信息分组：名称 / 存储ID / 技能类型 ---
        basic_info_group = QtWidgets.QGroupBox("基础信息")
        basic_info_layout = QtWidgets.QFormLayout(basic_info_group)
        basic_info_layout.setSpacing(Sizes.SPACING_SMALL)

        self.id_label = QtWidgets.QLabel("-")
        basic_info_layout.addRow("存储ID:", self.id_label)

        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("例如：单手武器-连段1")
        basic_info_layout.addRow("技能名称:", self.name_edit)

        self.skill_type_combo = QtWidgets.QComboBox()
        # 仅做 UI 标签，不直接绑定枚举，后续需要时可以接入实体配置中的 SkillType
        self.skill_type_combo.addItems(
            [
                "普通技能",
                "瞬发技能",
                "长按技能",
                "连段技能",
                "瞄准技能",
            ]
        )
        basic_info_layout.addRow("技能类型:", self.skill_type_combo)

        main_layout.addWidget(basic_info_group)

        # --- 基础设置 ---
        basic_group = QtWidgets.QGroupBox("基础设置")
        basic_layout = QtWidgets.QFormLayout(basic_group)
        basic_layout.setSpacing(Sizes.SPACING_SMALL)

        self.enable_cliff_protection_switch = ToggleSwitch()
        basic_layout.addRow("启用运动坠崖保护:", self.enable_cliff_protection_switch)

        self.can_use_in_air_switch = ToggleSwitch()
        basic_layout.addRow("是否可以在空中释放:", self.can_use_in_air_switch)

        self.skill_note_edit = QtWidgets.QTextEdit()
        self.skill_note_edit.setMinimumHeight(60)
        self.skill_note_edit.setMaximumHeight(140)
        self.skill_note_edit.setPlaceholderText("补充该技能的设计思路、使用说明或特殊注意事项...")
        basic_layout.addRow("技能备注:", self.skill_note_edit)

        main_layout.addWidget(basic_group)

        # --- 连段配置 ---
        combo_group = QtWidgets.QGroupBox("连段配置")
        combo_layout = QtWidgets.QFormLayout(combo_group)
        combo_layout.setSpacing(Sizes.SPACING_SMALL)

        self.enable_charge_branch_switch = ToggleSwitch()
        combo_layout.addRow("是否开启蓄力分支:", self.enable_charge_branch_switch)

        self.shared_charge_precast_switch = ToggleSwitch()
        combo_layout.addRow("蓄力公共前摇:", self.shared_charge_precast_switch)

        main_layout.addWidget(combo_group)

        # --- 数值配置 ---
        numeric_group = QtWidgets.QGroupBox("数值配置")
        numeric_layout = QtWidgets.QFormLayout(numeric_group)
        numeric_layout.setSpacing(Sizes.SPACING_SMALL)

        self.has_cooldown_switch = ToggleSwitch()
        self.cooldown_spin = QtWidgets.QDoubleSpinBox()
        self.cooldown_spin.setRange(0.0, 9999.0)
        self.cooldown_spin.setDecimals(2)
        self.cooldown_spin.setSuffix(" 秒")
        self.cooldown_spin.setSingleStep(0.1)

        numeric_layout.addRow("是否有冷却时间:", self.has_cooldown_switch)
        numeric_layout.addRow("冷却时间:", self.cooldown_spin)

        self.has_usage_limit_switch = ToggleSwitch()
        self.usage_count_spin = QtWidgets.QSpinBox()
        self.usage_count_spin.setRange(1, 9999)
        self.usage_count_spin.setValue(1)
        numeric_layout.addRow("是否有次数限制:", self.has_usage_limit_switch)
        numeric_layout.addRow("使用次数上限:", self.usage_count_spin)

        self.has_cost_switch = ToggleSwitch()
        self.cost_type_edit = QtWidgets.QLineEdit()
        self.cost_type_edit.setPlaceholderText("例如：stamina / mana / 自定义资源ID")
        self.cost_amount_spin = QtWidgets.QDoubleSpinBox()
        self.cost_amount_spin.setRange(0.0, 999999.0)
        self.cost_amount_spin.setDecimals(2)
        self.cost_amount_spin.setSingleStep(1.0)

        numeric_layout.addRow("是否有消耗:", self.has_cost_switch)
        numeric_layout.addRow("消耗类型:", self.cost_type_edit)
        numeric_layout.addRow("消耗量:", self.cost_amount_spin)

        self.target_range_type_combo = QtWidgets.QComboBox()
        self.target_range_type_combo.addItems(["圆柱体", "扇形"])
        numeric_layout.addRow("索敌范围:", self.target_range_type_combo)

        self.target_radius_spin = QtWidgets.QDoubleSpinBox()
        self.target_radius_spin.setRange(0.0, 9999.0)
        self.target_radius_spin.setDecimals(2)
        self.target_radius_spin.setValue(5.0)
        numeric_layout.addRow("半径 (m):", self.target_radius_spin)

        self.target_height_spin = QtWidgets.QDoubleSpinBox()
        self.target_height_spin.setRange(0.0, 9999.0)
        self.target_height_spin.setDecimals(2)
        self.target_height_spin.setValue(2.0)
        numeric_layout.addRow("高度 (m):", self.target_height_spin)

        main_layout.addWidget(numeric_group)

        # --- 生命周期管理 ---
        lifecycle_group = QtWidgets.QGroupBox("生命周期管理")
        lifecycle_layout = QtWidgets.QFormLayout(lifecycle_group)
        lifecycle_layout.setSpacing(Sizes.SPACING_SMALL)

        self.destroy_on_limit_switch = ToggleSwitch()
        self.max_usage_count_spin = QtWidgets.QSpinBox()
        self.max_usage_count_spin.setRange(0, 9999)
        self.max_usage_count_spin.setValue(0)

        lifecycle_layout.addRow(
            "达到次数上限是否销毁技能:", self.destroy_on_limit_switch
        )
        lifecycle_layout.addRow("生命周期次数上限:", self.max_usage_count_spin)

        main_layout.addWidget(lifecycle_group)
        main_layout.addStretch(1)

        # 绑定信号
        self._bind_signals()

    def _build_graphs_tab(self, page: QtWidgets.QWidget) -> None:
        """构建“节点图”标签页，复用通用 GraphsTab。"""
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.skill_graphs_tab = GraphsTab(page, graph_data_provider=None)
        self.skill_graphs_tab.set_service(self._graph_service)
        if self.resource_manager is not None:
            self.skill_graphs_tab.set_resource_manager(self.resource_manager)
        if self.package_index_manager is not None:
            self.skill_graphs_tab.set_package_index_manager(self.package_index_manager)

        # 技能节点图：仅允许绑定客户端节点图下“技能节点图”文件夹中的图
        # （对应 assets/资源库/节点图/client/技能节点图/*）
        self.skill_graphs_tab.set_allowed_graph_scope(
            graph_type="client",
            folder_prefix="技能节点图",
        )

        self.skill_graphs_tab.data_changed.connect(self._on_skill_graphs_tab_changed)
        self.skill_graphs_tab.graph_selected.connect(self.graph_selected.emit)

        layout.addWidget(self.skill_graphs_tab)

    def _bind_signals(self) -> None:
        self.name_edit.textChanged.connect(self._on_name_changed)
        self.skill_type_combo.currentIndexChanged.connect(self._on_skill_type_changed)

        self.enable_cliff_protection_switch.stateChanged.connect(
            self._on_enable_cliff_protection_changed
        )
        self.can_use_in_air_switch.stateChanged.connect(
            self._on_can_use_in_air_changed
        )
        self.skill_note_edit.textChanged.connect(self._on_skill_note_changed)

        self.enable_charge_branch_switch.stateChanged.connect(
            self._on_enable_charge_branch_changed
        )
        self.shared_charge_precast_switch.stateChanged.connect(
            self._on_shared_charge_precast_changed
        )

        self.has_cooldown_switch.stateChanged.connect(
            self._on_has_cooldown_changed
        )
        self.cooldown_spin.valueChanged.connect(self._on_cooldown_changed)

        self.has_usage_limit_switch.stateChanged.connect(
            self._on_has_usage_limit_changed
        )
        self.usage_count_spin.valueChanged.connect(self._on_usage_count_changed)

        self.has_cost_switch.stateChanged.connect(self._on_has_cost_changed)
        self.cost_type_edit.textChanged.connect(self._on_cost_type_changed)
        self.cost_amount_spin.valueChanged.connect(self._on_cost_amount_changed)

        self.target_range_type_combo.currentIndexChanged.connect(
            self._on_target_range_type_changed
        )
        self.target_radius_spin.valueChanged.connect(self._on_target_radius_changed)
        self.target_height_spin.valueChanged.connect(self._on_target_height_changed)

        self.destroy_on_limit_switch.stateChanged.connect(
            self._on_destroy_on_limit_changed
        )
        self.max_usage_count_spin.valueChanged.connect(
            self._on_max_usage_count_changed
        )

    # ------------------------------------------------------------------ 公共接口

    def set_context(
        self,
        package: Optional[PresetPackage],
        skill_id: Optional[str],
    ) -> None:
        """设置当前技能上下文并加载字段。"""
        self.current_package = package
        self.current_skill_id = skill_id

        if not package or not skill_id:
            self.current_skill_data = None
            self.skill_editor = _SkillEditorStruct(
                basic={},
                combo={},
                numeric={},
                lifecycle={},
            )
            self.skill_graphs_context = None
            if self.skill_graphs_tab is not None:
                self.skill_graphs_tab.clear()
            self._clear_ui()
            self.setEnabled(False)
            self._update_status_badge()
            return

        skill_map = package.combat_presets.skills
        skill_data = skill_map.get(skill_id)
        if not isinstance(skill_data, dict):
            self.current_skill_data = None
            self.skill_editor = _SkillEditorStruct(
                basic={},
                combo={},
                numeric={},
                lifecycle={},
            )
            self.skill_graphs_context = None
            if self.skill_graphs_tab is not None:
                self.skill_graphs_tab.clear()
            self._clear_ui()
            self.setEnabled(False)
            self._update_status_badge()
            return

        self.current_skill_data = skill_data

        metadata = skill_data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            skill_data["metadata"] = metadata

        skill_editor_raw = metadata.get("skill_editor")
        if not isinstance(skill_editor_raw, dict):
            skill_editor_raw = {}
            metadata["skill_editor"] = skill_editor_raw

        basic_section = skill_editor_raw.get("basic")
        if not isinstance(basic_section, dict):
            basic_section = {}
            skill_editor_raw["basic"] = basic_section

        combo_section = skill_editor_raw.get("combo")
        if not isinstance(combo_section, dict):
            combo_section = {}
            skill_editor_raw["combo"] = combo_section

        numeric_section = skill_editor_raw.get("numeric")
        if not isinstance(numeric_section, dict):
            numeric_section = {}
            skill_editor_raw["numeric"] = numeric_section

        lifecycle_section = skill_editor_raw.get("lifecycle")
        if not isinstance(lifecycle_section, dict):
            lifecycle_section = {}
            skill_editor_raw["lifecycle"] = lifecycle_section

        self.skill_editor = _SkillEditorStruct(
            basic=basic_section,
            combo=combo_section,
            numeric=numeric_section,
            lifecycle=lifecycle_section,
        )

        # 技能级节点图上下文（metadata.skill_editor.graphs / graph_variable_overrides）
        graphs_value = skill_editor_raw.get("graphs")
        if not isinstance(graphs_value, list):
            graphs_value = []
            skill_editor_raw["graphs"] = graphs_value

        overrides_value = skill_editor_raw.get("graph_variable_overrides")
        if not isinstance(overrides_value, dict):
            overrides_value = {}
            skill_editor_raw["graph_variable_overrides"] = overrides_value

        self.skill_graphs_context = SkillGraphsContext(
            default_graphs=graphs_value,
            graph_variable_overrides=overrides_value,
        )
        if self.skill_graphs_tab is not None:
            self.skill_graphs_tab.set_context(
                self.skill_graphs_context,
                "template",
                self.current_package,
                force=True,
            )

        self._load_fields()
        self._update_status_badge()
        self.setEnabled(True)

    # ------------------------------------------------------------------ 内部加载 & 状态

    def _clear_ui(self) -> None:
        """重置控件显示，但不修改底层数据字典。"""
        self.id_label.setText("-")

        self.name_edit.blockSignals(True)
        self.name_edit.clear()
        self.name_edit.blockSignals(False)

        self.skill_type_combo.blockSignals(True)
        self.skill_type_combo.setCurrentIndex(0)
        self.skill_type_combo.blockSignals(False)

        for switch_widget in (
            self.enable_cliff_protection_switch,
            self.can_use_in_air_switch,
            self.enable_charge_branch_switch,
            self.shared_charge_precast_switch,
            self.has_cooldown_switch,
            self.has_usage_limit_switch,
            self.has_cost_switch,
            self.destroy_on_limit_switch,
        ):
            switch_widget.blockSignals(True)
            switch_widget.setChecked(False)
            switch_widget.blockSignals(False)

        self.skill_note_edit.blockSignals(True)
        self.skill_note_edit.clear()
        self.skill_note_edit.blockSignals(False)

        self.cooldown_spin.blockSignals(True)
        self.cooldown_spin.setValue(0.0)
        self.cooldown_spin.blockSignals(False)

        self.usage_count_spin.blockSignals(True)
        self.usage_count_spin.setValue(1)
        self.usage_count_spin.blockSignals(False)

        self.cost_type_edit.blockSignals(True)
        self.cost_type_edit.clear()
        self.cost_type_edit.blockSignals(False)

        self.cost_amount_spin.blockSignals(True)
        self.cost_amount_spin.setValue(0.0)
        self.cost_amount_spin.blockSignals(False)

        self.target_range_type_combo.blockSignals(True)
        self.target_range_type_combo.setCurrentIndex(0)
        self.target_range_type_combo.blockSignals(False)

        self.target_radius_spin.blockSignals(True)
        self.target_radius_spin.setValue(5.0)
        self.target_radius_spin.blockSignals(False)

        self.target_height_spin.blockSignals(True)
        self.target_height_spin.setValue(2.0)
        self.target_height_spin.blockSignals(False)

        self.max_usage_count_spin.blockSignals(True)
        self.max_usage_count_spin.setValue(0)
        self.max_usage_count_spin.blockSignals(False)

        # 清空节点图页签上下文
        self.skill_graphs_context = None
        if self.skill_graphs_tab is not None:
            self.skill_graphs_tab.clear()

    def _load_fields(self) -> None:
        if not self.current_skill_data:
            self._clear_ui()
            return

        # 顶部基础信息
        self.id_label.setText(str(self.current_skill_id or "-"))

        name_value = str(self.current_skill_data.get("skill_name", "")).strip()
        self.name_edit.blockSignals(True)
        self.name_edit.setText(name_value)
        self.name_edit.blockSignals(False)

        type_text = str(self.current_skill_data.get("skill_type", "普通技能"))
        index = self.skill_type_combo.findText(type_text)
        if index < 0:
            index = 0
        self.skill_type_combo.blockSignals(True)
        self.skill_type_combo.setCurrentIndex(index)
        self.skill_type_combo.blockSignals(False)

        # 基础设置
        basic_section = self.skill_editor.basic
        self._set_switch_from_section(
            self.enable_cliff_protection_switch,
            basic_section,
            "enable_cliff_protection",
            False,
        )
        self._set_switch_from_section(
            self.can_use_in_air_switch,
            basic_section,
            "can_use_in_air",
            False,
        )

        note_text = str(basic_section.get("skill_note", "")).strip()
        self.skill_note_edit.blockSignals(True)
        self.skill_note_edit.setPlainText(note_text)
        self.skill_note_edit.blockSignals(False)

        # 连段配置
        combo_section = self.skill_editor.combo
        self._set_switch_from_section(
            self.enable_charge_branch_switch,
            combo_section,
            "enable_charge_branch",
            False,
        )
        self._set_switch_from_section(
            self.shared_charge_precast_switch,
            combo_section,
            "shared_charge_precast",
            False,
        )

        # 数值配置
        numeric_section = self.skill_editor.numeric
        self._set_switch_from_section(
            self.has_cooldown_switch,
            numeric_section,
            "has_cooldown",
            False,
        )

        cooldown_value = float(numeric_section.get("cooldown_time", 0.0))
        self.cooldown_spin.blockSignals(True)
        self.cooldown_spin.setValue(cooldown_value)
        self.cooldown_spin.blockSignals(False)

        self._set_switch_from_section(
            self.has_usage_limit_switch,
            numeric_section,
            "has_usage_limit",
            False,
        )
        usage_count_value = int(numeric_section.get("usage_count", 1))
        self.usage_count_spin.blockSignals(True)
        self.usage_count_spin.setValue(max(1, usage_count_value))
        self.usage_count_spin.blockSignals(False)

        self._set_switch_from_section(
            self.has_cost_switch,
            numeric_section,
            "has_cost",
            False,
        )

        cost_type_value = str(numeric_section.get("cost_type", "")).strip()
        self.cost_type_edit.blockSignals(True)
        self.cost_type_edit.setText(cost_type_value)
        self.cost_type_edit.blockSignals(False)

        cost_amount_value = float(numeric_section.get("cost_amount", 0.0))
        self.cost_amount_spin.blockSignals(True)
        self.cost_amount_spin.setValue(cost_amount_value)
        self.cost_amount_spin.blockSignals(False)

        range_type_text = str(numeric_section.get("target_range_type", "圆柱体"))
        range_index = self.target_range_type_combo.findText(range_type_text)
        if range_index < 0:
            range_index = 0
        self.target_range_type_combo.blockSignals(True)
        self.target_range_type_combo.setCurrentIndex(range_index)
        self.target_range_type_combo.blockSignals(False)

        radius_value = float(numeric_section.get("target_radius", 5.0))
        self.target_radius_spin.blockSignals(True)
        self.target_radius_spin.setValue(radius_value)
        self.target_radius_spin.blockSignals(False)

        height_value = float(numeric_section.get("target_height", 2.0))
        self.target_height_spin.blockSignals(True)
        self.target_height_spin.setValue(height_value)
        self.target_height_spin.blockSignals(False)

        # 生命周期管理
        lifecycle_section = self.skill_editor.lifecycle
        self._set_switch_from_section(
            self.destroy_on_limit_switch,
            lifecycle_section,
            "destroy_on_limit",
            False,
        )

        max_usage_value = int(lifecycle_section.get("max_usage_count", 0))
        self.max_usage_count_spin.blockSignals(True)
        self.max_usage_count_spin.setValue(max(0, max_usage_value))
        self.max_usage_count_spin.blockSignals(False)

        self._sync_numeric_controls_enabled_state()

    def _update_status_badge(self) -> None:
        if self._status_label is None:
            return
        if not self.current_skill_id or not self.current_skill_data:
            self._status_label.setText("未选中技能")
            self.update_status_badge_style(
                self._status_label,
                Colors.INFO_BG,
                Colors.TEXT_PRIMARY,
            )
            return
        display_name = (
            str(self.current_skill_data.get("skill_name", "")).strip()
            or self.current_skill_id
        )
        self._status_label.setText(f"技能 · {display_name}")
        self.update_status_badge_style(
            self._status_label,
            Colors.INFO_BG,
            Colors.PRIMARY,
        )

    @staticmethod
    def _set_switch_from_section(
        widget: ToggleSwitch,
        section: Dict[str, Any],
        key: str,
        default: bool,
    ) -> None:
        value = bool(section.get(key, default))
        widget.blockSignals(True)
        widget.setChecked(value)
        widget.blockSignals(False)

    def _mark_skill_modified(self) -> None:
        if not self.current_skill_data:
            return
        self.current_skill_data["last_modified"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def _sync_numeric_controls_enabled_state(self) -> None:
        self.cooldown_spin.setEnabled(self.has_cooldown_switch.isChecked())
        self.usage_count_spin.setEnabled(self.has_usage_limit_switch.isChecked())

        has_cost = self.has_cost_switch.isChecked()
        self.cost_type_edit.setEnabled(has_cost)
        self.cost_amount_spin.setEnabled(has_cost)

    # ------------------------------------------------------------------ 槽函数：节点图页签

    def _on_skill_graphs_tab_changed(self) -> None:
        """节点图标签页数据变化时写回 metadata.skill_editor.graphs 与变量覆盖。"""
        if not self.current_skill_data or not self.skill_graphs_context:
            return

        metadata = self.current_skill_data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            self.current_skill_data["metadata"] = metadata

        skill_editor_raw = metadata.get("skill_editor")
        if not isinstance(skill_editor_raw, dict):
            skill_editor_raw = {}
            metadata["skill_editor"] = skill_editor_raw

        skill_editor_raw["graphs"] = self.skill_graphs_context.default_graphs
        if self.skill_graphs_context.graph_variable_overrides:
            skill_editor_raw["graph_variable_overrides"] = (
                self.skill_graphs_context.graph_variable_overrides
            )
        else:
            skill_editor_raw.pop("graph_variable_overrides", None)

        self._mark_skill_modified()
        self.data_changed.emit()

    # ------------------------------------------------------------------ 槽函数：基础信息

    def _on_name_changed(self, text: str) -> None:
        if not self.current_skill_data:
            return
        self.current_skill_data["skill_name"] = text.strip()
        self._mark_skill_modified()
        self._update_status_badge()
        self.data_changed.emit()

    def _on_skill_type_changed(self, index: int) -> None:
        del index
        if not self.current_skill_data:
            return
        self.current_skill_data["skill_type"] = self.skill_type_combo.currentText()
        self._mark_skill_modified()
        self.data_changed.emit()

    # ------------------------------------------------------------------ 槽函数：基础设置

    def _on_enable_cliff_protection_changed(self, state: int) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.basic["enable_cliff_protection"] = (
            state == QtCore.Qt.CheckState.Checked.value
        )
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_can_use_in_air_changed(self, state: int) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.basic["can_use_in_air"] = (
            state == QtCore.Qt.CheckState.Checked.value
        )
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_skill_note_changed(self) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.basic["skill_note"] = self.skill_note_edit.toPlainText().strip()
        self._mark_skill_modified()
        self.data_changed.emit()

    # ------------------------------------------------------------------ 槽函数：连段配置

    def _on_enable_charge_branch_changed(self, state: int) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.combo["enable_charge_branch"] = (
            state == QtCore.Qt.CheckState.Checked.value
        )
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_shared_charge_precast_changed(self, state: int) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.combo["shared_charge_precast"] = (
            state == QtCore.Qt.CheckState.Checked.value
        )
        self._mark_skill_modified()
        self.data_changed.emit()

    # ------------------------------------------------------------------ 槽函数：数值配置

    def _on_has_cooldown_changed(self, state: int) -> None:
        if not self.current_skill_data:
            return
        has_cooldown = state == QtCore.Qt.CheckState.Checked.value
        self.skill_editor.numeric["has_cooldown"] = has_cooldown
        self._sync_numeric_controls_enabled_state()
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_cooldown_changed(self, value: float) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.numeric["cooldown_time"] = float(value)
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_has_usage_limit_changed(self, state: int) -> None:
        if not self.current_skill_data:
            return
        has_limit = state == QtCore.Qt.CheckState.Checked.value
        self.skill_editor.numeric["has_usage_limit"] = has_limit
        self._sync_numeric_controls_enabled_state()
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_usage_count_changed(self, value: int) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.numeric["usage_count"] = int(value)
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_has_cost_changed(self, state: int) -> None:
        if not self.current_skill_data:
            return
        has_cost = state == QtCore.Qt.CheckState.Checked.value
        self.skill_editor.numeric["has_cost"] = has_cost
        self._sync_numeric_controls_enabled_state()
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_cost_type_changed(self, text: str) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.numeric["cost_type"] = text.strip()
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_cost_amount_changed(self, value: float) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.numeric["cost_amount"] = float(value)
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_target_range_type_changed(self, index: int) -> None:
        del index
        if not self.current_skill_data:
            return
        self.skill_editor.numeric["target_range_type"] = (
            self.target_range_type_combo.currentText()
        )
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_target_radius_changed(self, value: float) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.numeric["target_radius"] = float(value)
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_target_height_changed(self, value: float) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.numeric["target_height"] = float(value)
        self._mark_skill_modified()
        self.data_changed.emit()

    # ------------------------------------------------------------------ 槽函数：生命周期管理

    def _on_destroy_on_limit_changed(self, state: int) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.lifecycle["destroy_on_limit"] = (
            state == QtCore.Qt.CheckState.Checked.value
        )
        self._mark_skill_modified()
        self.data_changed.emit()

    def _on_max_usage_count_changed(self, value: int) -> None:
        if not self.current_skill_data:
            return
        self.skill_editor.lifecycle["max_usage_count"] = int(value)
        self._mark_skill_modified()
        self.data_changed.emit()


__all__ = ["CombatSkillPanel"]



