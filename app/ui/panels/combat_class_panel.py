"""职业详情面板（战斗预设-职业）。

该面板在战斗预设模式下右侧显示，用于编辑单个“职业”预设的详细配置。

分为三个标签：
- 战斗：基础战斗属性、等级与经验、移动与镜头等设置（图1）
- 技能：普通攻击、主动技能与自定义按键技能（图2）
- 节点图：复用通用 GraphsTab，挂载职业相关节点图

数据结构约定：
- 职业资源基础字段由 `PlayerClassConfig` 提供（base_health/base_attack/base_defense/base_speed/skill_list）
- 该面板的扩展配置写入职业 JSON 的 `metadata.class_editor` 字段：
  - metadata.class_editor.battle: 战斗与成长相关字段
  - metadata.class_editor.skills: 技能与快捷键相关字段
  - metadata.class_editor.graphs: 职业层级挂载的节点图 ID 列表
  - metadata.class_editor.graph_variable_overrides: 节点图暴露变量覆盖
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

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


@dataclass
class _ClassEditorStruct:
    """内部使用的职业编辑结构，便于类型约束。"""

    battle: Dict[str, Any]
    skills: Dict[str, Any]


class CombatPlayerClassPanel(PanelScaffold):
    """职业详情面板。

    - 左上方状态徽章展示当前职业名
    - 主体为“战斗 / 技能 / 节点图”三个标签
    - 所有字段变更会更新职业 JSON 并通过 data_changed 信号通知外层立即持久化
    """

    data_changed = QtCore.pyqtSignal()
    graph_selected = QtCore.pyqtSignal(str, dict)

    def __init__(
        self,
        resource_manager: Optional[ResourceManager] = None,
        package_index_manager: Optional[PackageIndexManager] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            title="职业详情",
            description="配置职业在战斗中的基础属性、技能与节点图。",
        )

        self.resource_manager: Optional[ResourceManager] = resource_manager
        self.package_index_manager: Optional[PackageIndexManager] = package_index_manager

        self.current_package: Optional[PresetPackage] = None
        self.current_class_id: Optional[str] = None
        self.current_class_data: Optional[Dict[str, Any]] = None
        self.class_editor: _ClassEditorStruct = _ClassEditorStruct(battle={}, skills={})

        # 顶部状态徽章
        self._status_label = self.create_status_badge(
            "CombatPlayerClassStatusBadge",
            "未选中职业",
            background_color=Colors.INFO_BG,
            text_color=Colors.TEXT_PRIMARY,
        )

        # 节点图上下文与服务
        self._graph_service = TemplateInstanceService()
        self.class_graphs_context: Optional[_GraphBindingContext] = None
        self.class_graphs_tab: Optional[GraphsTab] = None

        # 主标签页
        self.main_tabs: QtWidgets.QTabWidget

        # === 战斗标签页控件 ===
        self.camera_combo: QtWidgets.QComboBox
        self.layout_combo: QtWidgets.QComboBox
        self.scan_rule_combo: QtWidgets.QComboBox

        self.allow_jump_switch: ToggleSwitch
        self.allow_dash_switch: ToggleSwitch
        self.allow_climb_switch: ToggleSwitch
        self.allow_slide_switch: ToggleSwitch

        self.initial_level_spin: QtWidgets.QSpinBox
        self.max_level_spin: QtWidgets.QSpinBox

        self.exp_mode_combo: QtWidgets.QComboBox
        self.exp_factor_spin: QtWidgets.QDoubleSpinBox
        self.exp_base_spin: QtWidgets.QDoubleSpinBox

        self.base_health_spin: QtWidgets.QDoubleSpinBox
        self.base_attack_spin: QtWidgets.QDoubleSpinBox
        self.base_defense_spin: QtWidgets.QDoubleSpinBox
        self.attribute_growth_combo: QtWidgets.QComboBox
        self.stamina_slider: QtWidgets.QSlider
        self.stamina_value_label: QtWidgets.QLabel

        # === 技能标签页控件 ===
        self.has_basic_attack_switch: ToggleSwitch
        self.basic_attack_combo: QtWidgets.QComboBox

        self.active_skill_count_spin: QtWidgets.QSpinBox
        self.active_skill_combos: List[QtWidgets.QComboBox] = []

        self.custom_skill_count_spin: QtWidgets.QSpinBox
        self.custom_skill_combos: List[QtWidgets.QComboBox] = []

        # 缓存当前可用技能选项：(display, skill_id)
        self._skill_options: List[Tuple[str, str]] = []

        self._build_ui()
        self.setEnabled(False)

    # ------------------------------------------------------------------ UI 构建

    def _build_ui(self) -> None:
        self.main_tabs = QtWidgets.QTabWidget()
        self.body_layout.addWidget(self.main_tabs, 1)

        battle_page = QtWidgets.QWidget()
        skills_page = QtWidgets.QWidget()
        graphs_page = QtWidgets.QWidget()

        self.main_tabs.addTab(battle_page, "战斗")
        self.main_tabs.addTab(skills_page, "技能")
        self.main_tabs.addTab(graphs_page, "节点图")

        self._build_battle_tab(battle_page)
        self._build_skills_tab(skills_page)
        self._build_graphs_tab(graphs_page)

    def _build_battle_tab(self, page: QtWidgets.QWidget) -> None:
        main_layout = QtWidgets.QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(Sizes.SPACING_MEDIUM)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        container = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(container)
        scroll_layout.setContentsMargins(
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
        )
        scroll_layout.setSpacing(Sizes.SPACING_MEDIUM)

        # --- 基础分组：镜头/布局/扫描规则 + 移动开关 -------------------------
        basic_group = QtWidgets.QGroupBox("基础")
        basic_layout = QtWidgets.QFormLayout(basic_group)
        basic_layout.setSpacing(Sizes.SPACING_SMALL)

        self.camera_combo = QtWidgets.QComboBox()
        self.camera_combo.setEditable(True)
        self.camera_combo.setPlaceholderText("选择或输入镜头ID")
        basic_layout.addRow("选择镜头:", self.camera_combo)

        self.layout_combo = QtWidgets.QComboBox()
        self.layout_combo.setEditable(True)
        self.layout_combo.setPlaceholderText("选择或输入布局ID")
        basic_layout.addRow("选择布局:", self.layout_combo)

        self.scan_rule_combo = QtWidgets.QComboBox()
        self.scan_rule_combo.addItems(
            [
                "视野中心距离",
                "固定顺序",
                "优先级权重",
            ]
        )
        basic_layout.addRow("扫描标签识别规则:", self.scan_rule_combo)

        movement_group = QtWidgets.QGroupBox()
        movement_layout = QtWidgets.QFormLayout(movement_group)
        movement_layout.setContentsMargins(0, 0, 0, 0)
        movement_layout.setSpacing(Sizes.SPACING_SMALL)

        self.allow_jump_switch = ToggleSwitch()
        self.allow_dash_switch = ToggleSwitch()
        self.allow_climb_switch = ToggleSwitch()
        self.allow_slide_switch = ToggleSwitch()

        movement_layout.addRow("允许跳跃:", self.allow_jump_switch)
        movement_layout.addRow("允许冲刺:", self.allow_dash_switch)
        movement_layout.addRow("允许攀爬:", self.allow_climb_switch)
        movement_layout.addRow("允许滑翔:", self.allow_slide_switch)

        basic_layout.addRow(movement_group)
        scroll_layout.addWidget(basic_group)

        # --- 等级分组 ------------------------------------------------------
        level_group = QtWidgets.QGroupBox("等级")
        level_layout = QtWidgets.QFormLayout(level_group)
        level_layout.setSpacing(Sizes.SPACING_SMALL)

        self.initial_level_spin = QtWidgets.QSpinBox()
        self.initial_level_spin.setRange(1, 999)
        self.initial_level_spin.setValue(1)
        level_layout.addRow("等级:", self.initial_level_spin)

        self.max_level_spin = QtWidgets.QSpinBox()
        self.max_level_spin.setRange(1, 999)
        self.max_level_spin.setValue(1)
        level_layout.addRow("最高等级:", self.max_level_spin)

        scroll_layout.addWidget(level_group)

        # --- 升级经验分组 ---------------------------------------------------
        exp_group = QtWidgets.QGroupBox("升级经验")
        exp_layout = QtWidgets.QFormLayout(exp_group)
        exp_layout.setSpacing(Sizes.SPACING_SMALL)

        self.exp_mode_combo = QtWidgets.QComboBox()
        self.exp_mode_combo.addItems(["线性公式", "自定义表格"])
        exp_layout.addRow("模式:", self.exp_mode_combo)

        formula_container = QtWidgets.QWidget()
        formula_layout = QtWidgets.QHBoxLayout(formula_container)
        formula_layout.setContentsMargins(0, 0, 0, 0)
        formula_layout.setSpacing(Sizes.SPACING_SMALL)

        prefix_label = QtWidgets.QLabel("当前等级 ×")
        self.exp_factor_spin = QtWidgets.QDoubleSpinBox()
        self.exp_factor_spin.setRange(0.0, 999999.0)
        self.exp_factor_spin.setDecimals(2)
        self.exp_factor_spin.setValue(0.0)

        plus_label = QtWidgets.QLabel("+")
        self.exp_base_spin = QtWidgets.QDoubleSpinBox()
        self.exp_base_spin.setRange(0.0, 999999.0)
        self.exp_base_spin.setDecimals(2)
        self.exp_base_spin.setValue(0.0)

        formula_layout.addWidget(prefix_label)
        formula_layout.addWidget(self.exp_factor_spin)
        formula_layout.addWidget(plus_label)
        formula_layout.addWidget(self.exp_base_spin)
        formula_layout.addStretch(1)

        exp_layout.addRow("公式:", formula_container)
        scroll_layout.addWidget(exp_group)

        # --- 基础战斗属性 --------------------------------------------------
        combat_group = QtWidgets.QGroupBox("基础战斗属性")
        combat_layout = QtWidgets.QFormLayout(combat_group)
        combat_layout.setSpacing(Sizes.SPACING_SMALL)

        self.base_health_spin = QtWidgets.QDoubleSpinBox()
        self.base_health_spin.setRange(0.0, 9999999.0)
        self.base_health_spin.setDecimals(2)
        self.base_health_spin.setValue(10000.0)
        combat_layout.addRow("基础生命值:", self.base_health_spin)

        self.base_attack_spin = QtWidgets.QDoubleSpinBox()
        self.base_attack_spin.setRange(0.0, 999999.0)
        self.base_attack_spin.setDecimals(2)
        self.base_attack_spin.setValue(500.0)
        combat_layout.addRow("基础攻击力:", self.base_attack_spin)

        self.base_defense_spin = QtWidgets.QDoubleSpinBox()
        self.base_defense_spin.setRange(0.0, 999999.0)
        self.base_defense_spin.setDecimals(2)
        self.base_defense_spin.setValue(500.0)
        combat_layout.addRow("基础防御力:", self.base_defense_spin)

        self.attribute_growth_combo = QtWidgets.QComboBox()
        self.attribute_growth_combo.addItems(["无成长", "线性成长", "指数成长"])
        combat_layout.addRow("属性成长:", self.attribute_growth_combo)

        stamina_container = QtWidgets.QWidget()
        stamina_layout = QtWidgets.QHBoxLayout(stamina_container)
        stamina_layout.setContentsMargins(0, 0, 0, 0)
        stamina_layout.setSpacing(Sizes.SPACING_SMALL)

        self.stamina_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.stamina_slider.setRange(0, 1000)
        self.stamina_slider.setValue(300)
        self.stamina_value_label = QtWidgets.QLabel("300.0")

        stamina_layout.addWidget(self.stamina_slider, 1)
        stamina_layout.addWidget(self.stamina_value_label)

        combat_layout.addRow("体力值上限:", stamina_container)
        scroll_layout.addWidget(combat_group)

        # --- 仇恨配置说明 --------------------------------------------------
        hate_group = QtWidgets.QGroupBox("仇恨配置")
        hate_layout = QtWidgets.QVBoxLayout(hate_group)
        hate_layout.setContentsMargins(Sizes.SPACING_SMALL, Sizes.SPACING_SMALL, Sizes.SPACING_SMALL, Sizes.SPACING_SMALL)
        hate_layout.setSpacing(Sizes.SPACING_SMALL)

        hate_label = QtWidgets.QLabel(
            "在「关卡设置」中的「仇恨类型」选择「自定义」类型后可配置相关内容。\n"
            "职业面板当前仅作为说明入口，不直接编辑仇恨规则。"
        )
        hate_label.setWordWrap(True)
        hate_layout.addWidget(hate_label)
        scroll_layout.addWidget(hate_group)

        scroll_layout.addStretch(1)
        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)

        # 绑定战斗相关信号
        self.camera_combo.currentTextChanged.connect(self._on_camera_changed)
        self.layout_combo.currentTextChanged.connect(self._on_layout_changed)
        self.scan_rule_combo.currentIndexChanged.connect(self._on_scan_rule_changed)

        self.allow_jump_switch.stateChanged.connect(self._on_allow_jump_changed)
        self.allow_dash_switch.stateChanged.connect(self._on_allow_dash_changed)
        self.allow_climb_switch.stateChanged.connect(self._on_allow_climb_changed)
        self.allow_slide_switch.stateChanged.connect(self._on_allow_slide_changed)

        self.initial_level_spin.valueChanged.connect(self._on_initial_level_changed)
        self.max_level_spin.valueChanged.connect(self._on_max_level_changed)

        self.exp_mode_combo.currentIndexChanged.connect(self._on_exp_mode_changed)
        self.exp_factor_spin.valueChanged.connect(self._on_exp_factor_changed)
        self.exp_base_spin.valueChanged.connect(self._on_exp_base_changed)

        self.base_health_spin.valueChanged.connect(self._on_base_health_changed)
        self.base_attack_spin.valueChanged.connect(self._on_base_attack_changed)
        self.base_defense_spin.valueChanged.connect(self._on_base_defense_changed)
        self.attribute_growth_combo.currentIndexChanged.connect(self._on_attribute_growth_changed)
        self.stamina_slider.valueChanged.connect(self._on_stamina_changed)

    def _build_skills_tab(self, page: QtWidgets.QWidget) -> None:
        """构建“技能”标签页。

        技能相关表单字段较多，采用 QScrollArea 包裹所有分组，保证右侧标签页高度固定，
        通过垂直滚动承载超出部分，避免随着技能槽位增多而撑大整个主窗口。
        """
        main_layout = QtWidgets.QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        main_layout.addWidget(scroll_area)

        container = QtWidgets.QWidget()
        scroll_area.setWidget(container)

        content_layout = QtWidgets.QVBoxLayout(container)
        content_layout.setContentsMargins(
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
        )
        content_layout.setSpacing(Sizes.SPACING_MEDIUM)

        # --- 普通攻击 -------------------------------------------------------
        basic_attack_group = QtWidgets.QGroupBox("普通攻击")
        basic_attack_layout = QtWidgets.QFormLayout(basic_attack_group)
        basic_attack_layout.setSpacing(Sizes.SPACING_SMALL)

        self.has_basic_attack_switch = ToggleSwitch()
        basic_attack_layout.addRow("是否有普通攻击:", self.has_basic_attack_switch)

        self.basic_attack_combo = QtWidgets.QComboBox()
        self.basic_attack_combo.setEditable(True)
        self.basic_attack_combo.setPlaceholderText("选择或输入普通攻击技能ID")
        basic_attack_layout.addRow("普通攻击:", self.basic_attack_combo)
        content_layout.addWidget(basic_attack_group)

        # --- 主动技能 -------------------------------------------------------
        active_group = QtWidgets.QGroupBox("主动技能")
        active_layout = QtWidgets.QFormLayout(active_group)
        active_layout.setSpacing(Sizes.SPACING_SMALL)

        self.active_skill_count_spin = QtWidgets.QSpinBox()
        self.active_skill_count_spin.setRange(0, 8)
        self.active_skill_count_spin.setValue(0)
        active_layout.addRow("主动技能数量:", self.active_skill_count_spin)

        self.active_skill_combos = []
        for slot_index in range(8):
            combo = QtWidgets.QComboBox()
            combo.setEditable(True)
            combo.setPlaceholderText(f"主动技能槽位{slot_index + 1}")
            combo.currentIndexChanged.connect(
                self._make_active_skill_changed_handler(slot_index)
            )
            self.active_skill_combos.append(combo)
            active_layout.addRow(f"槽位{slot_index + 1}:", combo)

        content_layout.addWidget(active_group)

        # --- 自定义按键技能 -------------------------------------------------
        custom_group = QtWidgets.QGroupBox("自定义按键技能")
        custom_layout = QtWidgets.QFormLayout(custom_group)
        custom_layout.setSpacing(Sizes.SPACING_SMALL)

        self.custom_skill_count_spin = QtWidgets.QSpinBox()
        self.custom_skill_count_spin.setRange(0, 8)
        self.custom_skill_count_spin.setValue(0)
        custom_layout.addRow("自定义技能数量:", self.custom_skill_count_spin)

        self.custom_skill_combos = []
        for slot_index in range(8):
            combo = QtWidgets.QComboBox()
            combo.setEditable(True)
            combo.setPlaceholderText(f"自定义技能槽位{slot_index + 1}")
            combo.currentIndexChanged.connect(
                self._make_custom_skill_changed_handler(slot_index)
            )
            self.custom_skill_combos.append(combo)
            custom_layout.addRow(f"槽位{slot_index + 1}:", combo)

        content_layout.addWidget(custom_group)
        content_layout.addStretch(1)

        # 绑定技能相关信号
        self.has_basic_attack_switch.stateChanged.connect(self._on_has_basic_attack_changed)
        self.basic_attack_combo.currentIndexChanged.connect(self._on_basic_attack_changed)

        self.active_skill_count_spin.valueChanged.connect(self._on_active_skill_count_changed)
        self.custom_skill_count_spin.valueChanged.connect(self._on_custom_skill_count_changed)

    def _build_graphs_tab(self, page: QtWidgets.QWidget) -> None:
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.class_graphs_tab = GraphsTab(page, graph_data_provider=None)
        self.class_graphs_tab.set_service(self._graph_service)
        if self.resource_manager is not None:
            self.class_graphs_tab.set_resource_manager(self.resource_manager)
        if self.package_index_manager is not None:
            self.class_graphs_tab.set_package_index_manager(self.package_index_manager)
        self.class_graphs_tab.data_changed.connect(self._on_graphs_tab_changed)
        self.class_graphs_tab.graph_selected.connect(self.graph_selected.emit)

        layout.addWidget(self.class_graphs_tab)

    # ------------------------------------------------------------------ 公共接口

    def set_context(self, package: Optional[PresetPackage], class_id: Optional[str]) -> None:
        """设置当前职业上下文。"""
        self.current_package = package
        self.current_class_id = class_id

        if not package or not class_id:
            self.current_class_data = None
            self.class_editor = _ClassEditorStruct(battle={}, skills={})
            self._clear_ui()
            self.setEnabled(False)
            self._update_status_badge()
            return

        class_map = package.combat_presets.player_classes
        class_data = class_map.get(class_id)
        if class_data is None:
            self.current_class_data = None
            self.class_editor = _ClassEditorStruct(battle={}, skills={})
            self._clear_ui()
            self.setEnabled(False)
            self._update_status_badge()
            return

        self.current_class_data = class_data

        metadata = class_data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            class_data["metadata"] = metadata

        class_editor_raw = metadata.get("class_editor")
        if not isinstance(class_editor_raw, dict):
            class_editor_raw = {}
            metadata["class_editor"] = class_editor_raw

        battle_section = class_editor_raw.get("battle")
        if not isinstance(battle_section, dict):
            battle_section = {}
            class_editor_raw["battle"] = battle_section

        skills_section = class_editor_raw.get("skills")
        if not isinstance(skills_section, dict):
            skills_section = {}
            class_editor_raw["skills"] = skills_section

        self.class_editor = _ClassEditorStruct(battle=battle_section, skills=skills_section)

        # 兼容旧数据：如未配置 skills 段落但已有 skill_list，则默认视作主动技能列表
        if "active_skills" not in skills_section:
            raw_skill_list = class_data.get("skill_list", [])
            if isinstance(raw_skill_list, list):
                normalized_skill_ids: List[str] = []
                for raw_id in raw_skill_list:
                    if isinstance(raw_id, str) and raw_id and raw_id not in normalized_skill_ids:
                        normalized_skill_ids.append(raw_id)
                if normalized_skill_ids:
                    skills_section["active_skills"] = normalized_skill_ids

        # 节点图上下文
        graphs_value = class_editor_raw.get("graphs")
        if not isinstance(graphs_value, list):
            graphs_value = []
            class_editor_raw["graphs"] = graphs_value

        overrides_value = class_editor_raw.get("graph_variable_overrides")
        if not isinstance(overrides_value, dict):
            overrides_value = {}
            class_editor_raw["graph_variable_overrides"] = overrides_value

        self.class_graphs_context = _GraphBindingContext(
            default_graphs=graphs_value,
            graph_variable_overrides=overrides_value,
        )
        if self.class_graphs_tab is not None:
            self.class_graphs_tab.set_context(
                self.class_graphs_context,
                "template",
                self.current_package,
                force=True,
            )

        # 刷新技能选项与 UI 显示
        self._refresh_skill_options()
        self._load_battle_fields()
        self._load_skill_fields()
        self._update_status_badge()
        self.setEnabled(True)

    # ------------------------------------------------------------------ 状态徽章

    def _update_status_badge(self) -> None:
        if self._status_label is None:
            return
        if not self.current_class_id or not self.current_class_data:
            self._status_label.setText("未选中职业")
            self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.TEXT_PRIMARY)
            return
        name_value = self.current_class_data.get("class_name", "")
        display_name = str(name_value).strip() or self.current_class_id
        self._status_label.setText(f"职业 · {display_name}")
        self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.PRIMARY)

    # ------------------------------------------------------------------ 清空与加载

    def _clear_ui(self) -> None:
        """清空界面显示内容。"""
        # 战斗
        self.camera_combo.blockSignals(True)
        self.camera_combo.setCurrentText("")
        self.camera_combo.blockSignals(False)

        self.layout_combo.blockSignals(True)
        self.layout_combo.setCurrentText("")
        self.layout_combo.blockSignals(False)

        self.scan_rule_combo.blockSignals(True)
        self.scan_rule_combo.setCurrentIndex(0)
        self.scan_rule_combo.blockSignals(False)

        for switch_widget in (
            self.allow_jump_switch,
            self.allow_dash_switch,
            self.allow_climb_switch,
            self.allow_slide_switch,
        ):
            switch_widget.blockSignals(True)
            switch_widget.setChecked(False)
            switch_widget.blockSignals(False)

        self.initial_level_spin.blockSignals(True)
        self.initial_level_spin.setValue(1)
        self.initial_level_spin.blockSignals(False)

        self.max_level_spin.blockSignals(True)
        self.max_level_spin.setValue(1)
        self.max_level_spin.blockSignals(False)

        self.exp_mode_combo.blockSignals(True)
        self.exp_mode_combo.setCurrentIndex(0)
        self.exp_mode_combo.blockSignals(False)

        self.exp_factor_spin.blockSignals(True)
        self.exp_factor_spin.setValue(0.0)
        self.exp_factor_spin.blockSignals(False)

        self.exp_base_spin.blockSignals(True)
        self.exp_base_spin.setValue(0.0)
        self.exp_base_spin.blockSignals(False)

        self.base_health_spin.blockSignals(True)
        self.base_health_spin.setValue(10000.0)
        self.base_health_spin.blockSignals(False)

        self.base_attack_spin.blockSignals(True)
        self.base_attack_spin.setValue(500.0)
        self.base_attack_spin.blockSignals(False)

        self.base_defense_spin.blockSignals(True)
        self.base_defense_spin.setValue(500.0)
        self.base_defense_spin.blockSignals(False)

        self.attribute_growth_combo.blockSignals(True)
        self.attribute_growth_combo.setCurrentIndex(0)
        self.attribute_growth_combo.blockSignals(False)

        self.stamina_slider.blockSignals(True)
        self.stamina_slider.setValue(300)
        self.stamina_slider.blockSignals(False)
        self.stamina_value_label.setText("300.0")

        # 技能
        self.has_basic_attack_switch.blockSignals(True)
        self.has_basic_attack_switch.setChecked(False)
        self.has_basic_attack_switch.blockSignals(False)

        self.basic_attack_combo.blockSignals(True)
        self.basic_attack_combo.setCurrentIndex(-1)
        self.basic_attack_combo.setCurrentText("")
        self.basic_attack_combo.blockSignals(False)

        self.active_skill_count_spin.blockSignals(True)
        self.active_skill_count_spin.setValue(0)
        self.active_skill_count_spin.blockSignals(False)

        for combo in self.active_skill_combos:
            combo.blockSignals(True)
            combo.setCurrentIndex(-1)
            combo.setCurrentText("")
            combo.blockSignals(False)

        self.custom_skill_count_spin.blockSignals(True)
        self.custom_skill_count_spin.setValue(0)
        self.custom_skill_count_spin.blockSignals(False)

        for combo in self.custom_skill_combos:
            combo.blockSignals(True)
            combo.setCurrentIndex(-1)
            combo.setCurrentText("")
            combo.blockSignals(False)

        # 节点图
        self.class_graphs_context = None
        if self.class_graphs_tab is not None:
            self.class_graphs_tab.clear()

    def _load_battle_fields(self) -> None:
        if not self.current_class_data:
            self._clear_ui()
            return

        battle_section = self.class_editor.battle

        camera_id = str(battle_section.get("camera_id", "")).strip()
        self.camera_combo.blockSignals(True)
        self.camera_combo.setCurrentText(camera_id)
        self.camera_combo.blockSignals(False)

        layout_id = str(battle_section.get("layout_id", "")).strip()
        self.layout_combo.blockSignals(True)
        self.layout_combo.setCurrentText(layout_id)
        self.layout_combo.blockSignals(False)

        scan_rule_value = str(battle_section.get("scan_rule", "视野中心距离"))
        scan_index = self.scan_rule_combo.findText(scan_rule_value)
        if scan_index < 0:
            scan_index = 0
        self.scan_rule_combo.blockSignals(True)
        self.scan_rule_combo.setCurrentIndex(scan_index)
        self.scan_rule_combo.blockSignals(False)

        self._set_switch_from_battle_key(self.allow_jump_switch, "allow_jump", default=False)
        self._set_switch_from_battle_key(self.allow_dash_switch, "allow_dash", default=False)
        self._set_switch_from_battle_key(self.allow_climb_switch, "allow_climb", default=False)
        self._set_switch_from_battle_key(self.allow_slide_switch, "allow_slide", default=False)

        initial_level_raw = battle_section.get("initial_level", self.current_class_data.get("initial_level", 1))
        max_level_raw = battle_section.get("max_level", self.current_class_data.get("max_level", 1))

        self.initial_level_spin.blockSignals(True)
        self.initial_level_spin.setValue(int(initial_level_raw))
        self.initial_level_spin.blockSignals(False)

        self.max_level_spin.blockSignals(True)
        self.max_level_spin.setValue(int(max_level_raw))
        self.max_level_spin.blockSignals(False)

        exp_mode_text = str(battle_section.get("exp_mode", "线性公式"))
        exp_mode_index = self.exp_mode_combo.findText(exp_mode_text)
        if exp_mode_index < 0:
            exp_mode_index = 0
        self.exp_mode_combo.blockSignals(True)
        self.exp_mode_combo.setCurrentIndex(exp_mode_index)
        self.exp_mode_combo.blockSignals(False)

        self.exp_factor_spin.blockSignals(True)
        self.exp_factor_spin.setValue(float(battle_section.get("exp_factor", 0.0)))
        self.exp_factor_spin.blockSignals(False)

        self.exp_base_spin.blockSignals(True)
        self.exp_base_spin.setValue(float(battle_section.get("exp_base", 0.0)))
        self.exp_base_spin.blockSignals(False)

        self.base_health_spin.blockSignals(True)
        self.base_health_spin.setValue(float(self.current_class_data.get("base_health", 100.0)))
        self.base_health_spin.blockSignals(False)

        self.base_attack_spin.blockSignals(True)
        self.base_attack_spin.setValue(float(self.current_class_data.get("base_attack", 10.0)))
        self.base_attack_spin.blockSignals(False)

        self.base_defense_spin.blockSignals(True)
        self.base_defense_spin.setValue(float(self.current_class_data.get("base_defense", 5.0)))
        self.base_defense_spin.blockSignals(False)

        growth_mode_text = str(battle_section.get("attribute_growth", "无成长"))
        growth_index = self.attribute_growth_combo.findText(growth_mode_text)
        if growth_index < 0:
            growth_index = 0
        self.attribute_growth_combo.blockSignals(True)
        self.attribute_growth_combo.setCurrentIndex(growth_index)
        self.attribute_growth_combo.blockSignals(False)

        stamina_value = float(battle_section.get("stamina_max", 300.0))
        stamina_slider_value = int(max(0.0, min(1000.0, stamina_value)))
        self.stamina_slider.blockSignals(True)
        self.stamina_slider.setValue(stamina_slider_value)
        self.stamina_slider.blockSignals(False)
        self.stamina_value_label.setText(f"{stamina_value:.1f}")

    def _load_skill_fields(self) -> None:
        if not self.current_class_data:
            self._clear_ui()
            return

        skills_section = self.class_editor.skills

        # 普通攻击
        has_basic_attack = bool(skills_section.get("has_basic_attack", False))
        basic_attack_id = str(skills_section.get("basic_attack_id", "")).strip()

        self.has_basic_attack_switch.blockSignals(True)
        self.has_basic_attack_switch.setChecked(has_basic_attack)
        self.has_basic_attack_switch.blockSignals(False)

        self._set_combo_to_skill_id(self.basic_attack_combo, basic_attack_id)

        # 主动技能
        active_skills_raw = skills_section.get("active_skills", [])
        active_skill_ids: List[str] = []
        if isinstance(active_skills_raw, list):
            for raw_id in active_skills_raw:
                if isinstance(raw_id, str) and raw_id:
                    active_skill_ids.append(raw_id)

        active_count = len(active_skill_ids)
        self.active_skill_count_spin.blockSignals(True)
        self.active_skill_count_spin.setValue(active_count)
        self.active_skill_count_spin.blockSignals(False)

        for slot_index, combo in enumerate(self.active_skill_combos):
            desired_id = active_skill_ids[slot_index] if slot_index < active_count else ""
            combo.blockSignals(True)
            self._set_combo_to_skill_id(combo, desired_id)
            combo.blockSignals(False)
            combo.setEnabled(slot_index < active_count)

        # 自定义按键技能
        custom_skills_raw = skills_section.get("custom_skills", [])
        custom_skill_ids: List[str] = []
        if isinstance(custom_skills_raw, list):
            for raw_id in custom_skills_raw:
                if isinstance(raw_id, str) and raw_id:
                    custom_skill_ids.append(raw_id)

        custom_count = len(custom_skill_ids)
        self.custom_skill_count_spin.blockSignals(True)
        self.custom_skill_count_spin.setValue(custom_count)
        self.custom_skill_count_spin.blockSignals(False)

        for slot_index, combo in enumerate(self.custom_skill_combos):
            desired_id = custom_skill_ids[slot_index] if slot_index < custom_count else ""
            combo.blockSignals(True)
            self._set_combo_to_skill_id(combo, desired_id)
            combo.blockSignals(False)
            combo.setEnabled(slot_index < custom_count)

        # 同步 skill_list 字段
        self._update_skill_list_field()

    def _set_switch_from_battle_key(
        self,
        widget: ToggleSwitch,
        key: str,
        default: bool,
    ) -> None:
        battle_section = self.class_editor.battle
        value = bool(battle_section.get(key, default))
        widget.blockSignals(True)
        widget.setChecked(value)
        widget.blockSignals(False)

    # ------------------------------------------------------------------ 技能选项

    def _refresh_skill_options(self) -> None:
        """根据当前包刷新技能下拉选项。"""
        self._skill_options = []

        package = self.current_package
        if package is None:
            self._rebuild_all_skill_combos()
            return

        skills_mapping = package.combat_presets.skills
        for skill_id, payload in skills_mapping.items():
            if not isinstance(skill_id, str) or not skill_id:
                continue
            name_value = ""
            if isinstance(payload, dict):
                name_value = str(payload.get("skill_name", "")).strip()
            display_name = name_value or skill_id
            self._skill_options.append((f"{display_name} ({skill_id})", skill_id))

        self._skill_options.sort(key=lambda pair: pair[0])
        self._rebuild_all_skill_combos()

    def _rebuild_all_skill_combos(self) -> None:
        combos: List[QtWidgets.QComboBox] = (
            [self.basic_attack_combo] + self.active_skill_combos + self.custom_skill_combos
        )
        for combo in combos:
            current_id = ""
            current_data = combo.currentData(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(current_data, str):
                current_id = current_data

            combo.blockSignals(True)
            combo.clear()
            combo.addItem("（未选择）", "")
            for display_text, skill_id in self._skill_options:
                combo.addItem(display_text, skill_id)
            combo.blockSignals(False)

            if current_id:
                self._set_combo_to_skill_id(combo, current_id)

    def _set_combo_to_skill_id(self, combo: QtWidgets.QComboBox, skill_id: str) -> None:
        """根据 skill_id 在下拉框中选择对应项，没有则保持空选。"""
        if not skill_id:
            combo.setCurrentIndex(0)
            return
        target_index = 0
        for row_index in range(combo.count()):
            user_data = combo.itemData(row_index, QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(user_data, str) and user_data == skill_id:
                target_index = row_index
                break
        combo.setCurrentIndex(target_index)

    # ------------------------------------------------------------------ 修改标记

    def _mark_class_modified(self) -> None:
        if not self.current_class_data:
            return
        self.current_class_data["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------ 槽函数：战斗

    def _on_camera_changed(self, text: str) -> None:
        if not self.current_class_data:
            return
        self.class_editor.battle["camera_id"] = text.strip()
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_layout_changed(self, text: str) -> None:
        if not self.current_class_data:
            return
        self.class_editor.battle["layout_id"] = text.strip()
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_scan_rule_changed(self, index: int) -> None:
        if not self.current_class_data:
            return
        rule_text = self.scan_rule_combo.itemText(index)
        self.class_editor.battle["scan_rule"] = rule_text
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_allow_jump_changed(self, state: int) -> None:
        if not self.current_class_data:
            return
        self.class_editor.battle["allow_jump"] = state == QtCore.Qt.CheckState.Checked.value
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_allow_dash_changed(self, state: int) -> None:
        if not self.current_class_data:
            return
        self.class_editor.battle["allow_dash"] = state == QtCore.Qt.CheckState.Checked.value
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_allow_climb_changed(self, state: int) -> None:
        if not self.current_class_data:
            return
        self.class_editor.battle["allow_climb"] = state == QtCore.Qt.CheckState.Checked.value
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_allow_slide_changed(self, state: int) -> None:
        if not self.current_class_data:
            return
        self.class_editor.battle["allow_slide"] = state == QtCore.Qt.CheckState.Checked.value
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_initial_level_changed(self, value: int) -> None:
        if not self.current_class_data:
            return
        self.class_editor.battle["initial_level"] = int(value)
        self.current_class_data["initial_level"] = int(value)
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_max_level_changed(self, value: int) -> None:
        if not self.current_class_data:
            return
        self.class_editor.battle["max_level"] = int(value)
        self.current_class_data["max_level"] = int(value)
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_exp_mode_changed(self, index: int) -> None:
        if not self.current_class_data:
            return
        mode_text = self.exp_mode_combo.itemText(index)
        self.class_editor.battle["exp_mode"] = mode_text
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_exp_factor_changed(self, value: float) -> None:
        if not self.current_class_data:
            return
        self.class_editor.battle["exp_factor"] = float(value)
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_exp_base_changed(self, value: float) -> None:
        if not self.current_class_data:
            return
        self.class_editor.battle["exp_base"] = float(value)
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_base_health_changed(self, value: float) -> None:
        if not self.current_class_data:
            return
        self.current_class_data["base_health"] = float(value)
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_base_attack_changed(self, value: float) -> None:
        if not self.current_class_data:
            return
        self.current_class_data["base_attack"] = float(value)
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_base_defense_changed(self, value: float) -> None:
        if not self.current_class_data:
            return
        self.current_class_data["base_defense"] = float(value)
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_attribute_growth_changed(self, index: int) -> None:
        if not self.current_class_data:
            return
        growth_text = self.attribute_growth_combo.itemText(index)
        self.class_editor.battle["attribute_growth"] = growth_text
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_stamina_changed(self, slider_value: int) -> None:
        if not self.current_class_data:
            return
        stamina_value = float(slider_value)
        self.class_editor.battle["stamina_max"] = stamina_value
        self.stamina_value_label.setText(f"{stamina_value:.1f}")
        self._mark_class_modified()
        self.data_changed.emit()

    # ------------------------------------------------------------------ 槽函数：技能

    def _on_has_basic_attack_changed(self, state: int) -> None:
        if not self.current_class_data:
            return
        has_basic_attack = state == QtCore.Qt.CheckState.Checked.value
        self.class_editor.skills["has_basic_attack"] = has_basic_attack
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_basic_attack_changed(self, _index: int) -> None:
        if not self.current_class_data:
            return
        skill_id = self._get_skill_id_from_combo(self.basic_attack_combo)
        self.class_editor.skills["basic_attack_id"] = skill_id
        self._update_skill_list_field()
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_active_skill_count_changed(self, value: int) -> None:
        if not self.current_class_data:
            return
        count = int(max(0, min(len(self.active_skill_combos), value)))
        self.class_editor.skills["active_skill_count"] = count
        for slot_index, combo in enumerate(self.active_skill_combos):
            combo.setEnabled(slot_index < count)
        self._update_active_skills_from_ui()
        self._update_skill_list_field()
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_custom_skill_count_changed(self, value: int) -> None:
        if not self.current_class_data:
            return
        count = int(max(0, min(len(self.custom_skill_combos), value)))
        self.class_editor.skills["custom_skill_count"] = count
        for slot_index, combo in enumerate(self.custom_skill_combos):
            combo.setEnabled(slot_index < count)
        self._update_custom_skills_from_ui()
        self._update_skill_list_field()
        self._mark_class_modified()
        self.data_changed.emit()

    def _make_active_skill_changed_handler(self, slot_index: int):
        def handler(_index: int) -> None:
            self._on_active_skill_changed(slot_index)

        return handler

    def _make_custom_skill_changed_handler(self, slot_index: int):
        def handler(_index: int) -> None:
            self._on_custom_skill_changed(slot_index)

        return handler

    def _on_active_skill_changed(self, slot_index: int) -> None:
        if not self.current_class_data:
            return
        self._update_active_skills_from_ui()
        self._update_skill_list_field()
        self._mark_class_modified()
        self.data_changed.emit()

    def _on_custom_skill_changed(self, slot_index: int) -> None:  # noqa: ARG002
        if not self.current_class_data:
            return
        self._update_custom_skills_from_ui()
        self._update_skill_list_field()
        self._mark_class_modified()
        self.data_changed.emit()

    def _get_skill_id_from_combo(self, combo: QtWidgets.QComboBox) -> str:
        user_data = combo.currentData(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(user_data, str):
            return user_data
        return combo.currentText().strip()

    def _update_active_skills_from_ui(self) -> None:
        skills: List[str] = []
        desired_count = int(self.active_skill_count_spin.value())
        for slot_index, combo in enumerate(self.active_skill_combos):
            if slot_index >= desired_count:
                break
            skill_id = self._get_skill_id_from_combo(combo)
            if skill_id:
                skills.append(skill_id)
        self.class_editor.skills["active_skills"] = skills

    def _update_custom_skills_from_ui(self) -> None:
        skills: List[str] = []
        desired_count = int(self.custom_skill_count_spin.value())
        for slot_index, combo in enumerate(self.custom_skill_combos):
            if slot_index >= desired_count:
                break
            skill_id = self._get_skill_id_from_combo(combo)
            if skill_id:
                skills.append(skill_id)
        self.class_editor.skills["custom_skills"] = skills

    def _update_skill_list_field(self) -> None:
        """根据技能配置更新职业主记录中的 skill_list 字段。"""
        if not self.current_class_data:
            return

        skills_section = self.class_editor.skills
        aggregated_ids: List[str] = []

        basic_attack_id = str(skills_section.get("basic_attack_id", "")).strip()
        if basic_attack_id:
            aggregated_ids.append(basic_attack_id)

        for key in ("active_skills", "custom_skills"):
            value = skills_section.get(key, [])
            if not isinstance(value, list):
                continue
            for skill_id in value:
                if not isinstance(skill_id, str) or not skill_id:
                    continue
                if skill_id not in aggregated_ids:
                    aggregated_ids.append(skill_id)

        self.current_class_data["skill_list"] = aggregated_ids

    # ------------------------------------------------------------------ 节点图

    def _on_graphs_tab_changed(self) -> None:
        """节点图标签页数据变化时写回 metadata.class_editor。"""
        if not self.current_class_data or not self.class_graphs_context:
            return

        metadata = self.current_class_data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            self.current_class_data["metadata"] = metadata

        class_editor_raw = metadata.get("class_editor")
        if not isinstance(class_editor_raw, dict):
            class_editor_raw = {}
            metadata["class_editor"] = class_editor_raw

        class_editor_raw["graphs"] = self.class_graphs_context.default_graphs
        if self.class_graphs_context.graph_variable_overrides:
            class_editor_raw["graph_variable_overrides"] = self.class_graphs_context.graph_variable_overrides
        else:
            class_editor_raw.pop("graph_variable_overrides", None)

        self._mark_class_modified()
        self.data_changed.emit()


__all__ = ["CombatPlayerClassPanel"]



