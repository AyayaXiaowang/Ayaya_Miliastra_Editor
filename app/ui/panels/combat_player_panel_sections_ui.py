"""
CombatPlayerEditorPanel 拆分模块：UI 构建与 UI 清理。

仅包含 UI 结构搭建与界面重置，不包含业务写回逻辑。
"""

from __future__ import annotations

from typing import Any, List, Optional

from PyQt6 import QtWidgets

from engine.graph.models.entity_templates import get_all_variable_types
from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.toggle_switch import ToggleSwitch
from app.ui.panels.combat_ability_components import CombatSettingsSection
from app.ui.panels.template_instance.graphs_tab import GraphsTab
from app.ui.widgets.two_row_field_table_widget import TwoRowFieldTableWidget


class CombatPlayerPanelSectionsUIMixin:
    player_edit_page: QtWidgets.QWidget
    role_edit_page: QtWidgets.QWidget

    player_sub_tabs: QtWidgets.QTabWidget
    role_sub_tabs: QtWidgets.QTabWidget

    player_selection_checkboxes: List[QtWidgets.QCheckBox]
    all_players_checkbox: QtWidgets.QCheckBox

    level_spin: QtWidgets.QSpinBox
    spawn_point_combo: QtWidgets.QComboBox
    profession_combo: QtWidgets.QComboBox

    allow_resurrection_check: ToggleSwitch
    show_resurrection_ui_check: ToggleSwitch
    resurrection_time_spin: QtWidgets.QDoubleSpinBox
    auto_resurrection_check: ToggleSwitch
    resurrection_count_limit_check: ToggleSwitch
    resurrection_count_spin: QtWidgets.QSpinBox
    resurrection_points_edit: QtWidgets.QPlainTextEdit
    resurrection_point_rule_combo: QtWidgets.QComboBox
    resurrection_health_ratio_spin: QtWidgets.QDoubleSpinBox
    special_knockout_pct_spin: QtWidgets.QDoubleSpinBox

    role_play_own_sound_switch: ToggleSwitch
    role_attributes_edit: QtWidgets.QPlainTextEdit
    role_combat_settings_section: Optional[CombatSettingsSection]

    player_graphs_tab: Optional[GraphsTab]
    role_graphs_tab: Optional[GraphsTab]
    player_custom_variable_table: TwoRowFieldTableWidget
    role_custom_variable_table: TwoRowFieldTableWidget
    player_ingame_save_template_combo: QtWidgets.QComboBox
    player_ingame_save_summary_label: QtWidgets.QLabel
    player_ingame_save_table: TwoRowFieldTableWidget
    _graph_service: Any

    resource_manager: Optional[Any]
    package_index_manager: Optional[Any]

    def _build_player_edit_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.player_edit_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_MEDIUM)

        self.player_sub_tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.player_sub_tabs, 1)

        # 玩家编辑 > 属性
        player_attr_page = QtWidgets.QWidget()
        attr_main_layout = QtWidgets.QVBoxLayout(player_attr_page)
        attr_main_layout.setContentsMargins(
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
        )
        attr_main_layout.setSpacing(Sizes.SPACING_MEDIUM)

        # 创建滚动区域
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_container = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_container)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(Sizes.SPACING_MEDIUM)

        # === 生效目标分组 ===
        target_group = QtWidgets.QGroupBox("生效目标")
        target_layout = QtWidgets.QVBoxLayout(target_group)
        target_layout.setSpacing(Sizes.SPACING_SMALL)

        self.player_selection_checkboxes = []
        players_widget = QtWidgets.QWidget()
        players_layout = QtWidgets.QGridLayout(players_widget)
        players_layout.setContentsMargins(0, 0, 0, 0)
        players_layout.setSpacing(Sizes.SPACING_SMALL)

        for index, player_index in enumerate(range(1, 9)):
            checkbox = QtWidgets.QCheckBox(f"玩家{player_index}")
            checkbox.setProperty("player_index", player_index)
            self.player_selection_checkboxes.append(checkbox)
            row = index // 4
            column = index % 4
            players_layout.addWidget(checkbox, row, column)

        self.all_players_checkbox = QtWidgets.QCheckBox("全部玩家")
        players_layout.addWidget(self.all_players_checkbox, 0, 4, 2, 1)

        target_layout.addWidget(players_widget)
        scroll_layout.addWidget(target_group)

        # === 基础分组 ===
        basic_group = QtWidgets.QGroupBox("基础")
        basic_layout = QtWidgets.QFormLayout(basic_group)
        basic_layout.setSpacing(Sizes.SPACING_SMALL)

        self.level_spin = QtWidgets.QSpinBox()
        self.level_spin.setRange(1, 999)
        self.level_spin.setValue(1)
        basic_layout.addRow("等级:", self.level_spin)

        self.spawn_point_combo = QtWidgets.QComboBox()
        self.spawn_point_combo.setEditable(True)
        self.spawn_point_combo.setPlaceholderText("选择或输入出生点ID")
        basic_layout.addRow("出生点:", self.spawn_point_combo)

        self.profession_combo = QtWidgets.QComboBox()
        self.profession_combo.setEditable(True)
        self.profession_combo.setPlaceholderText("选择或输入职业ID")
        basic_layout.addRow("初始职业:", self.profession_combo)

        scroll_layout.addWidget(basic_group)

        # === 复苏分组 ===
        resurrection_group = QtWidgets.QGroupBox("复苏")
        resurrection_layout = QtWidgets.QFormLayout(resurrection_group)
        resurrection_layout.setSpacing(Sizes.SPACING_SMALL)

        self.allow_resurrection_check = ToggleSwitch()
        resurrection_layout.addRow("允许复苏:", self.allow_resurrection_check)

        self.show_resurrection_ui_check = ToggleSwitch()
        resurrection_layout.addRow("显示复苏页面:", self.show_resurrection_ui_check)

        self.resurrection_time_spin = QtWidgets.QDoubleSpinBox()
        self.resurrection_time_spin.setRange(0.0, 9999.0)
        self.resurrection_time_spin.setSingleStep(0.5)
        self.resurrection_time_spin.setSuffix(" 秒")
        self.resurrection_time_spin.setValue(5.0)
        resurrection_layout.addRow("复苏耗时:", self.resurrection_time_spin)

        self.auto_resurrection_check = ToggleSwitch()
        resurrection_layout.addRow("自动复苏:", self.auto_resurrection_check)

        self.resurrection_count_limit_check = ToggleSwitch()
        resurrection_layout.addRow("复苏次数限制:", self.resurrection_count_limit_check)

        self.resurrection_count_spin = QtWidgets.QSpinBox()
        self.resurrection_count_spin.setRange(0, 999)
        self.resurrection_count_spin.setValue(3)
        resurrection_layout.addRow("复苏次数:", self.resurrection_count_spin)

        self.resurrection_points_edit = QtWidgets.QPlainTextEdit()
        self.resurrection_points_edit.setPlaceholderText("复苏点列表，每行一个ID")
        self.resurrection_points_edit.setMaximumHeight(60)
        resurrection_layout.addRow("复苏点列表:", self.resurrection_points_edit)

        self.resurrection_point_rule_combo = QtWidgets.QComboBox()
        self.resurrection_point_rule_combo.addItems(
            [
                "最近的复苏点",
                "最新激活的复苏点",
                "优先级最高的复苏点",
                "随机复苏点",
            ]
        )
        resurrection_layout.addRow("复苏点选取规则:", self.resurrection_point_rule_combo)

        self.resurrection_health_ratio_spin = QtWidgets.QDoubleSpinBox()
        self.resurrection_health_ratio_spin.setRange(0.0, 100.0)
        self.resurrection_health_ratio_spin.setSingleStep(5.0)
        self.resurrection_health_ratio_spin.setSuffix(" %")
        self.resurrection_health_ratio_spin.setValue(50.0)
        resurrection_layout.addRow("复苏后生命比例(%):", self.resurrection_health_ratio_spin)

        scroll_layout.addWidget(resurrection_group)

        # === 特殊被击倒损伤分组 ===
        special_damage_group = QtWidgets.QGroupBox("特殊被击倒损伤")
        special_damage_layout = QtWidgets.QFormLayout(special_damage_group)
        special_damage_layout.setSpacing(Sizes.SPACING_SMALL)

        self.special_knockout_pct_spin = QtWidgets.QDoubleSpinBox()
        self.special_knockout_pct_spin.setRange(0.0, 100.0)
        self.special_knockout_pct_spin.setSingleStep(1.0)
        self.special_knockout_pct_spin.setSuffix(" %")
        self.special_knockout_pct_spin.setValue(0.0)
        special_damage_layout.addRow("扣除最大生命值比例(%):", self.special_knockout_pct_spin)

        scroll_layout.addWidget(special_damage_group)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_container)
        attr_main_layout.addWidget(scroll_area)

        self.player_sub_tabs.addTab(player_attr_page, "属性")

        # 玩家编辑 > 自定义变量
        player_variables_page = QtWidgets.QWidget()
        player_variables_layout = QtWidgets.QVBoxLayout(player_variables_page)
        player_variables_layout.setContentsMargins(0, 0, 0, 0)
        player_variables_layout.setSpacing(Sizes.SPACING_SMALL)

        # 工具条：添加 / 删除自定义变量
        player_variables_toolbar = QtWidgets.QHBoxLayout()
        player_variables_toolbar.setContentsMargins(
            Sizes.SPACING_SMALL,
            Sizes.SPACING_SMALL,
            Sizes.SPACING_SMALL,
            Sizes.SPACING_SMALL,
        )
        player_variables_toolbar.setSpacing(Sizes.SPACING_SMALL)

        player_add_button = QtWidgets.QPushButton("+ 添加自定义变量", player_variables_page)
        player_remove_button = QtWidgets.QPushButton("删除", player_variables_page)
        player_add_button.clicked.connect(self._add_player_custom_variable)
        player_remove_button.clicked.connect(self._remove_player_custom_variable)

        player_variables_toolbar.addWidget(player_add_button)
        player_variables_toolbar.addWidget(player_remove_button)
        player_variables_toolbar.addStretch(1)

        player_variables_layout.addLayout(player_variables_toolbar)

        self.player_custom_variable_table = TwoRowFieldTableWidget(
            get_all_variable_types(),
            parent=player_variables_page,
        )
        player_variables_layout.addWidget(self.player_custom_variable_table)
        self.player_sub_tabs.addTab(player_variables_page, "自定义变量")

        # 玩家编辑 > 自定义变量_局内存档变量
        player_ingame_save_page = QtWidgets.QWidget()
        player_ingame_save_layout = QtWidgets.QVBoxLayout(player_ingame_save_page)
        player_ingame_save_layout.setContentsMargins(0, 0, 0, 0)
        player_ingame_save_layout.setSpacing(Sizes.SPACING_SMALL)

        # 模板选择分组
        ingame_template_group = QtWidgets.QGroupBox("局内存档管理模板")
        ingame_template_form = QtWidgets.QFormLayout(ingame_template_group)
        ingame_template_form.setSpacing(Sizes.SPACING_SMALL)

        self.player_ingame_save_template_combo = QtWidgets.QComboBox(ingame_template_group)
        self.player_ingame_save_template_combo.setEditable(False)
        self.player_ingame_save_template_combo.setMinimumWidth(220)
        ingame_template_form.addRow("选择模板:", self.player_ingame_save_template_combo)

        self.player_ingame_save_summary_label = QtWidgets.QLabel("未选择局内存档管理模板。")
        self.player_ingame_save_summary_label.setWordWrap(True)
        ingame_template_form.addRow("概要:", self.player_ingame_save_summary_label)

        player_ingame_save_layout.addWidget(ingame_template_group)

        # 使用滚动区域承载 chip 变量表格，便于后续扩展
        ingame_scroll_area = QtWidgets.QScrollArea(player_ingame_save_page)
        ingame_scroll_area.setWidgetResizable(True)
        ingame_scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        ingame_scroll_container = QtWidgets.QWidget()
        ingame_scroll_layout = QtWidgets.QVBoxLayout(ingame_scroll_container)
        ingame_scroll_layout.setContentsMargins(
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
        )
        ingame_scroll_layout.setSpacing(Sizes.SPACING_SMALL)

        # 局内存档 chip_* 变量表格：第四列用于展示每个槽位对应结构体及最大条目数概要。
        chip_column_headers = ["序号", "变量名", "数据类型", "最大条目数"]
        self.player_ingame_save_table = TwoRowFieldTableWidget(
            ["结构体"],
            parent=ingame_scroll_container,
            column_headers=chip_column_headers,
        )
        # 该表格仅作为局内存档模板 entries 的只读视图，值列展示结构体名称+最大条目数等元信息。
        self.player_ingame_save_table.set_value_mode("metadata")
        self.player_ingame_save_table.setEnabled(False)
        ingame_scroll_layout.addWidget(self.player_ingame_save_table)
        ingame_scroll_layout.addStretch(1)

        ingame_scroll_area.setWidget(ingame_scroll_container)
        player_ingame_save_layout.addWidget(ingame_scroll_area, 1)

        self.player_sub_tabs.addTab(player_ingame_save_page, "自定义变量_局内存档变量")

        # 玩家编辑 > 通用组件（当前仅占位说明）
        player_components_page = QtWidgets.QWidget()
        components_layout = QtWidgets.QVBoxLayout(player_components_page)
        components_layout.setContentsMargins(0, 0, 0, 0)
        components_layout.setSpacing(Sizes.SPACING_SMALL)
        components_hint = QtWidgets.QLabel(
            "玩家层级的通用组件挂载将在后续版本接入独立的组件编辑器，本标签页目前仅作为结构占位。"
        )
        components_hint.setWordWrap(True)
        components_layout.addWidget(components_hint)
        components_layout.addStretch(1)
        self.player_sub_tabs.addTab(player_components_page, "通用组件")

        # 玩家编辑 > 节点图（使用通用 GraphsTab，支持挂载节点图与暴露变量覆盖）
        player_graphs_page = QtWidgets.QWidget()
        graphs_layout = QtWidgets.QVBoxLayout(player_graphs_page)
        graphs_layout.setContentsMargins(0, 0, 0, 0)
        graphs_layout.setSpacing(0)

        self.player_graphs_tab = GraphsTab(player_graphs_page, graph_data_provider=None)
        self.player_graphs_tab.set_service(self._graph_service)
        if self.resource_manager is not None:
            self.player_graphs_tab.set_resource_manager(self.resource_manager)
        if self.package_index_manager is not None:
            self.player_graphs_tab.set_package_index_manager(self.package_index_manager)
        self.player_graphs_tab.data_changed.connect(self._on_player_graphs_tab_changed)
        self.player_graphs_tab.graph_selected.connect(self.graph_selected.emit)

        graphs_layout.addWidget(self.player_graphs_tab)
        self.player_sub_tabs.addTab(player_graphs_page, "节点图")

        # 绑定信号
        self.all_players_checkbox.stateChanged.connect(self._on_all_players_changed)
        for checkbox in self.player_selection_checkboxes:
            checkbox.stateChanged.connect(self._on_player_selection_changed)
        self.level_spin.valueChanged.connect(self._on_level_changed)
        self.spawn_point_combo.currentTextChanged.connect(self._on_spawn_point_changed)
        self.profession_combo.currentTextChanged.connect(self._on_profession_changed)
        self.allow_resurrection_check.stateChanged.connect(self._on_allow_resurrection_changed)
        self.show_resurrection_ui_check.stateChanged.connect(self._on_show_resurrection_ui_changed)
        self.resurrection_time_spin.valueChanged.connect(self._on_resurrection_time_changed)
        self.auto_resurrection_check.stateChanged.connect(self._on_auto_resurrection_changed)
        self.resurrection_count_limit_check.stateChanged.connect(
            self._on_resurrection_count_limit_changed
        )
        self.resurrection_count_spin.valueChanged.connect(self._on_resurrection_count_changed)
        self.resurrection_points_edit.textChanged.connect(self._on_resurrection_points_changed)
        self.resurrection_point_rule_combo.currentIndexChanged.connect(
            self._on_resurrection_point_rule_changed
        )
        self.resurrection_health_ratio_spin.valueChanged.connect(
            self._on_resurrection_health_ratio_changed
        )
        self.special_knockout_pct_spin.valueChanged.connect(self._on_special_knockout_changed)
        self.player_custom_variable_table.field_changed.connect(
            self._on_player_custom_variables_changed
        )
        self.player_custom_variable_table.field_added.connect(
            self._on_player_custom_variables_changed
        )
        self.player_custom_variable_table.field_deleted.connect(
            self._on_player_custom_variables_changed
        )
        self.player_custom_variable_table.struct_view_requested.connect(
            self._on_struct_view_requested
        )
        self.player_ingame_save_template_combo.currentIndexChanged.connect(
            self._on_player_ingame_save_template_changed
        )
        self.player_ingame_save_table.field_changed.connect(
            self._on_player_ingame_save_variables_changed
        )
        self.player_ingame_save_table.field_added.connect(
            self._on_player_ingame_save_variables_changed
        )
        self.player_ingame_save_table.field_deleted.connect(
            self._on_player_ingame_save_variables_changed
        )
        self.player_ingame_save_table.struct_view_requested.connect(
            self._on_struct_view_requested
        )

    def _build_role_edit_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.role_edit_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_MEDIUM)

        # 角色编辑子标签：属性 / 自定义变量 / 能力 / 通用组件 / 节点图
        self.role_sub_tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.role_sub_tabs, 1)

        # 角色编辑 > 属性：音效开关 + 属性说明
        role_attr_page = QtWidgets.QWidget()
        role_attr_layout = QtWidgets.QVBoxLayout(role_attr_page)
        role_attr_layout.setContentsMargins(0, 0, 0, 0)
        role_attr_layout.setSpacing(Sizes.SPACING_MEDIUM)

        sound_group = QtWidgets.QGroupBox("音效")
        sound_layout = QtWidgets.QFormLayout(sound_group)
        sound_layout.setSpacing(Sizes.SPACING_SMALL)

        sound_label = QtWidgets.QLabel("是否播放自身音效:")
        self.role_play_own_sound_switch = ToggleSwitch()
        sound_layout.addRow(sound_label, self.role_play_own_sound_switch)

        role_attr_layout.addWidget(sound_group)

        self.role_attributes_edit = QtWidgets.QPlainTextEdit()
        self.role_attributes_edit.setPlaceholderText(
            "该角色在当前玩家模板下的属性说明，可按需记录字段与数值。"
        )
        role_attr_layout.addWidget(self.role_attributes_edit, 1)

        self.role_sub_tabs.addTab(role_attr_page, "属性")

        # 角色编辑 > 自定义变量
        role_variables_page = QtWidgets.QWidget()
        role_variables_layout = QtWidgets.QVBoxLayout(role_variables_page)
        role_variables_layout.setContentsMargins(0, 0, 0, 0)
        role_variables_layout.setSpacing(Sizes.SPACING_SMALL)

        # 工具条：添加 / 删除自定义变量
        role_variables_toolbar = QtWidgets.QHBoxLayout()
        role_variables_toolbar.setContentsMargins(
            Sizes.SPACING_SMALL,
            Sizes.SPACING_SMALL,
            Sizes.SPACING_SMALL,
            Sizes.SPACING_SMALL,
        )
        role_variables_toolbar.setSpacing(Sizes.SPACING_SMALL)

        role_add_button = QtWidgets.QPushButton("+ 添加自定义变量", role_variables_page)
        role_remove_button = QtWidgets.QPushButton("删除", role_variables_page)
        role_add_button.clicked.connect(self._add_role_custom_variable)
        role_remove_button.clicked.connect(self._remove_role_custom_variable)

        role_variables_toolbar.addWidget(role_add_button)
        role_variables_toolbar.addWidget(role_remove_button)
        role_variables_toolbar.addStretch(1)

        role_variables_layout.addLayout(role_variables_toolbar)

        self.role_custom_variable_table = TwoRowFieldTableWidget(
            get_all_variable_types(),
            parent=role_variables_page,
        )
        role_variables_layout.addWidget(self.role_custom_variable_table)
        self.role_sub_tabs.addTab(role_variables_page, "自定义变量")

        role_ability_page = self._build_role_ability_tab()
        self.role_sub_tabs.addTab(role_ability_page, "能力")

        role_components_page = QtWidgets.QWidget()
        role_components_layout = QtWidgets.QVBoxLayout(role_components_page)
        role_components_layout.setContentsMargins(0, 0, 0, 0)
        role_components_layout.setSpacing(Sizes.SPACING_SMALL)
        role_components_hint = QtWidgets.QLabel(
            "角色层级的通用组件挂载将在后续版本接入独立的组件编辑器，本标签页目前仅作为结构占位。"
        )
        role_components_hint.setWordWrap(True)
        role_components_layout.addWidget(role_components_hint)
        role_components_layout.addStretch(1)
        self.role_sub_tabs.addTab(role_components_page, "通用组件")

        # 角色编辑 > 节点图（使用通用 GraphsTab，挂载角色层级节点图）
        self.role_graphs_tab = GraphsTab(self.role_sub_tabs, graph_data_provider=None)
        self.role_graphs_tab.set_service(self._graph_service)
        if self.resource_manager is not None:
            self.role_graphs_tab.set_resource_manager(self.resource_manager)
        if self.package_index_manager is not None:
            self.role_graphs_tab.set_package_index_manager(self.package_index_manager)
        self.role_graphs_tab.data_changed.connect(self._on_role_graphs_tab_changed)
        self.role_graphs_tab.graph_selected.connect(self.graph_selected.emit)
        self.role_sub_tabs.addTab(self.role_graphs_tab, "节点图")

        # 绑定角色相关信号
        self.role_play_own_sound_switch.toggled.connect(self._on_role_play_own_sound_changed)
        self.role_attributes_edit.textChanged.connect(self._on_role_attributes_changed)
        self.role_custom_variable_table.field_changed.connect(
            self._on_role_custom_variables_changed
        )
        self.role_custom_variable_table.field_added.connect(self._on_role_custom_variables_changed)
        self.role_custom_variable_table.field_deleted.connect(
            self._on_role_custom_variables_changed
        )

    def _build_role_ability_tab(self) -> QtWidgets.QWidget:
        ability_page = QtWidgets.QWidget()
        ability_layout = QtWidgets.QVBoxLayout(ability_page)
        ability_layout.setContentsMargins(0, 0, 0, 0)
        ability_layout.setSpacing(Sizes.SPACING_MEDIUM)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        scroll_container = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_container)
        scroll_layout.setContentsMargins(
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
        )
        scroll_layout.setSpacing(Sizes.SPACING_MEDIUM)

        self.role_combat_settings_section = CombatSettingsSection(scroll_container)
        self.role_combat_settings_section.changed.connect(self._on_role_combat_settings_changed)
        scroll_layout.addWidget(self.role_combat_settings_section)

        scroll_layout.addStretch()

        scroll_area.setWidget(scroll_container)
        ability_layout.addWidget(scroll_area, 1)

        return ability_page

    @staticmethod
    def _wrap_plain_text(editor: QtWidgets.QPlainTextEdit) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(editor)
        return container

    def _clear_ui(self) -> None:
        """清空界面显示内容。"""
        # 清空玩家选择
        self.all_players_checkbox.blockSignals(True)
        self.all_players_checkbox.setChecked(False)
        self.all_players_checkbox.blockSignals(False)

        for checkbox in self.player_selection_checkboxes:
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)

        # 清空基础属性
        self.level_spin.blockSignals(True)
        self.level_spin.setValue(1)
        self.level_spin.blockSignals(False)

        self.spawn_point_combo.blockSignals(True)
        self.spawn_point_combo.clear()
        self.spawn_point_combo.blockSignals(False)

        self.profession_combo.blockSignals(True)
        self.profession_combo.clear()
        self.profession_combo.blockSignals(False)

        # 清空复苏属性
        self.allow_resurrection_check.blockSignals(True)
        self.allow_resurrection_check.setChecked(False)
        self.allow_resurrection_check.blockSignals(False)

        self.show_resurrection_ui_check.blockSignals(True)
        self.show_resurrection_ui_check.setChecked(False)
        self.show_resurrection_ui_check.blockSignals(False)

        self.resurrection_time_spin.blockSignals(True)
        self.resurrection_time_spin.setValue(5.0)
        self.resurrection_time_spin.blockSignals(False)

        self.auto_resurrection_check.blockSignals(True)
        self.auto_resurrection_check.setChecked(False)
        self.auto_resurrection_check.blockSignals(False)

        self.resurrection_count_limit_check.blockSignals(True)
        self.resurrection_count_limit_check.setChecked(False)
        self.resurrection_count_limit_check.blockSignals(False)

        self.resurrection_count_spin.blockSignals(True)
        self.resurrection_count_spin.setValue(3)
        self.resurrection_count_spin.blockSignals(False)

        self.resurrection_points_edit.blockSignals(True)
        self.resurrection_points_edit.clear()
        self.resurrection_points_edit.blockSignals(False)

        self.resurrection_point_rule_combo.blockSignals(True)
        self.resurrection_point_rule_combo.setCurrentIndex(0)
        self.resurrection_point_rule_combo.blockSignals(False)

        self.resurrection_health_ratio_spin.blockSignals(True)
        self.resurrection_health_ratio_spin.setValue(50.0)
        self.resurrection_health_ratio_spin.blockSignals(False)

        # 清空特殊损伤
        self.special_knockout_pct_spin.blockSignals(True)
        self.special_knockout_pct_spin.setValue(0.0)
        self.special_knockout_pct_spin.blockSignals(False)

        # 清空角色音效开关
        self.role_play_own_sound_switch.blockSignals(True)
        self.role_play_own_sound_switch.setChecked(False)
        self.role_play_own_sound_switch.blockSignals(False)

        if self.role_combat_settings_section is not None:
            self.role_combat_settings_section.set_from_metadata(None)

        # 清空角色编辑
        self.role_attributes_edit.blockSignals(True)
        self.role_attributes_edit.clear()
        self.role_attributes_edit.blockSignals(False)

        # 清空自定义变量
        self.player_custom_variable_table.clear_fields()
        self.role_custom_variable_table.clear_fields()

        # 清空局内存档变量视图
        if hasattr(self, "player_ingame_save_template_combo"):
            self.player_ingame_save_template_combo.blockSignals(True)
            self.player_ingame_save_template_combo.clear()
            self.player_ingame_save_template_combo.blockSignals(False)
        if hasattr(self, "player_ingame_save_summary_label"):
            self.player_ingame_save_summary_label.setText("未选择局内存档管理模板。")
        if hasattr(self, "player_ingame_save_table"):
            self.player_ingame_save_table.clear_fields()
            self.player_ingame_save_table.setEnabled(False)

        # 清空节点图上下文
        self.player_graphs_context = None
        self.role_graphs_context = None
        if self.player_graphs_tab is not None:
            self.player_graphs_tab.clear()
        if self.role_graphs_tab is not None:
            self.role_graphs_tab.clear()


