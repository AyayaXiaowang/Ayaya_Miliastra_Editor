"""
CombatPlayerEditorPanel 辅助模块。

本模块通过 Mixin 的形式承载“玩家编辑 / 角色编辑 / 节点图上下文”的
UI 构建与字段读写逻辑，使主面板文件保持精简，仅负责上下文管理、
状态徽章与所属存档行等高层职责。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6 import QtCore, QtWidgets

from engine.configs.resource_types import ResourceType
from engine.graph.models.entity_templates import get_all_variable_types
from engine.resources.definition_schema_view import (
    get_default_definition_schema_view,
)
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.level_variable_schema_view import (
    get_default_level_variable_schema_view,
)
from engine.utils.name_utils import generate_unique_name
from ui.dialogs.struct_viewer_dialog import StructViewerDialog
from ui.foundation.theme_manager import Sizes
from ui.foundation.toggle_switch import ToggleSwitch
from ui.panels.combat_ability_components import CombatSettingsSection
from ui.panels.template_instance.graphs_tab import GraphsTab
from ui.widgets.two_row_field_table_widget import TwoRowFieldTableWidget


@dataclass
class _PlayerEditorStruct:
    """内部使用的玩家编辑结构，方便类型约束。"""

    player: Dict[str, Any]
    role: Dict[str, Any]


@dataclass
class _GraphBindingContext:
    """为 GraphsTab 提供的轻量上下文对象。

    仅暴露:
    - default_graphs: 当前对象挂载的节点图 ID 列表
    - graph_variable_overrides: 节点图暴露变量覆盖字典
    """

    default_graphs: List[str]
    graph_variable_overrides: Dict[str, Dict[str, object]]


class CombatPlayerPanelSectionsMixin:
    """CombatPlayerEditorPanel 的 UI 构建与字段绑定逻辑。

    主面板负责：
    - 当前包 / 模板上下文管理
    - 状态徽章与标题
    - 所属存档行与索引写回
    - 模板级别的 last_modified 维护

    本 Mixin 负责：
    - 玩家编辑与角色编辑子标签页的 UI 构建
    - 字段加载与写回 metadata.player_editor
    - 玩家/角色层级节点图 GraphsTab 的上下文管理
    """

    # 由主面板在 __init__ 中提供的属性，仅作类型提示，不在此初始化
    resource_manager: Optional[Any]
    package_index_manager: Optional[Any]
    current_package: Optional[Any]
    current_template_data: Optional[Dict[str, Any]]
    player_editor: _PlayerEditorStruct
    player_graphs_context: Optional[_GraphBindingContext]
    role_graphs_context: Optional[_GraphBindingContext]

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

        chip_column_headers = ["序号", "变量名", "结构体", "数据值"]
        self.player_ingame_save_table = TwoRowFieldTableWidget(
            ["结构体"],
            parent=ingame_scroll_container,
            column_headers=chip_column_headers,
        )
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

    # ------------------------------------------------------------------ 玩家编辑数据加载/写回

    def _load_player_fields(self) -> None:
        if not self.current_template_data:
            self._clear_ui()
            return

        template = self.current_template_data
        player_section = self.player_editor.player

        # 加载生效目标
        selected_players = player_section.get("selected_players", [])
        all_players_selected = player_section.get("all_players", False)

        self.all_players_checkbox.blockSignals(True)
        self.all_players_checkbox.setChecked(all_players_selected)
        self.all_players_checkbox.blockSignals(False)

        for checkbox in self.player_selection_checkboxes:
            player_index = checkbox.property("player_index")
            checkbox.blockSignals(True)
            checkbox.setChecked(player_index in selected_players)
            checkbox.blockSignals(False)

        # 加载基础属性
        self.level_spin.blockSignals(True)
        self.level_spin.setValue(int(template.get("level", 1)))
        self.level_spin.blockSignals(False)

        spawn_point = str(player_section.get("spawn_point", "")).strip()
        self.spawn_point_combo.blockSignals(True)
        self.spawn_point_combo.setCurrentText(spawn_point)
        self.spawn_point_combo.blockSignals(False)

        profession_id = str(template.get("default_profession_id", "")).strip()
        self.profession_combo.blockSignals(True)
        self.profession_combo.setCurrentText(profession_id)
        self.profession_combo.blockSignals(False)

        # 加载复苏属性
        resurrection_data = player_section.get("resurrection", {})
        if not isinstance(resurrection_data, dict):
            resurrection_data = {}

        self.allow_resurrection_check.blockSignals(True)
        self.allow_resurrection_check.setChecked(
            resurrection_data.get("allow_resurrection", False)
        )
        self.allow_resurrection_check.blockSignals(False)

        self.show_resurrection_ui_check.blockSignals(True)
        self.show_resurrection_ui_check.setChecked(resurrection_data.get("show_ui", False))
        self.show_resurrection_ui_check.blockSignals(False)

        self.resurrection_time_spin.blockSignals(True)
        self.resurrection_time_spin.setValue(float(resurrection_data.get("time", 5.0)))
        self.resurrection_time_spin.blockSignals(False)

        self.auto_resurrection_check.blockSignals(True)
        self.auto_resurrection_check.setChecked(
            resurrection_data.get("auto_resurrection", False)
        )
        self.auto_resurrection_check.blockSignals(False)

        self.resurrection_count_limit_check.blockSignals(True)
        self.resurrection_count_limit_check.setChecked(
            resurrection_data.get("count_limit", False)
        )
        self.resurrection_count_limit_check.blockSignals(False)

        self.resurrection_count_spin.blockSignals(True)
        self.resurrection_count_spin.setValue(int(resurrection_data.get("count", 3)))
        self.resurrection_count_spin.blockSignals(False)

        resurrection_points = resurrection_data.get("points", [])
        if isinstance(resurrection_points, list):
            points_text = "\n".join(str(p) for p in resurrection_points)
        else:
            points_text = str(resurrection_points).strip()
        self.resurrection_points_edit.blockSignals(True)
        self.resurrection_points_edit.setPlainText(points_text)
        self.resurrection_points_edit.blockSignals(False)

        rule_mapping = {
            "nearest": 0,
            "latest_activated": 1,
            "highest_priority": 2,
            "random": 3,
        }
        rule = resurrection_data.get("point_rule", "nearest")
        rule_index = rule_mapping.get(rule, 0)
        self.resurrection_point_rule_combo.blockSignals(True)
        self.resurrection_point_rule_combo.setCurrentIndex(rule_index)
        self.resurrection_point_rule_combo.blockSignals(False)

        self.resurrection_health_ratio_spin.blockSignals(True)
        self.resurrection_health_ratio_spin.setValue(
            float(resurrection_data.get("health_ratio", 50.0))
        )
        self.resurrection_health_ratio_spin.blockSignals(False)

        # 加载特殊被击倒损伤
        self.special_knockout_pct_spin.blockSignals(True)
        self.special_knockout_pct_spin.setValue(
            float(player_section.get("special_knockout_pct", 0.0))
        )
        self.special_knockout_pct_spin.blockSignals(False)

        # 加载玩家层级自定义变量（不包含局内存档 chip 变量）
        self._load_player_custom_variables()

        # 加载局内存档模板绑定与 chip 变量视图
        self._load_player_ingame_save_binding()

    # ------------------------------------------------------------------ 节点图上下文与写回

    def _setup_player_graphs_context(self) -> None:
        """根据 metadata.player_editor.player 为玩家层级构建节点图上下文。"""
        if not self.current_template_data or self.player_graphs_tab is None:
            self.player_graphs_context = None
            if self.player_graphs_tab is not None:
                self.player_graphs_tab.clear()
            return

        player_section = self.player_editor.player
        graphs_value = player_section.get("graphs")
        if not isinstance(graphs_value, list):
            graphs_value = []
            player_section["graphs"] = graphs_value

        overrides_value = player_section.get("graph_variable_overrides")
        if not isinstance(overrides_value, dict):
            overrides_value = {}
            player_section["graph_variable_overrides"] = overrides_value

        self.player_graphs_context = _GraphBindingContext(
            default_graphs=graphs_value,
            graph_variable_overrides=overrides_value,
        )
        self.player_graphs_tab.set_context(
            self.player_graphs_context,
            "template",
            self.current_package,
            force=True,
        )

    def _setup_role_graphs_context(self) -> None:
        """根据 metadata.player_editor.role 为角色层级构建节点图上下文。"""
        if not self.current_template_data or self.role_graphs_tab is None:
            self.role_graphs_context = None
            if self.role_graphs_tab is not None:
                self.role_graphs_tab.clear()
            return

        role_section = self.player_editor.role
        graphs_value = role_section.get("graphs")
        if not isinstance(graphs_value, list):
            graphs_value = []
            role_section["graphs"] = graphs_value

        overrides_value = role_section.get("graph_variable_overrides")
        if not isinstance(overrides_value, dict):
            overrides_value = {}
            role_section["graph_variable_overrides"] = overrides_value

        self.role_graphs_context = _GraphBindingContext(
            default_graphs=graphs_value,
            graph_variable_overrides=overrides_value,
        )
        self.role_graphs_tab.set_context(
            self.role_graphs_context,
            "template",
            self.current_package,
            force=True,
        )

    def _load_player_custom_variables(self) -> None:
        """根据 metadata 与 metadata.player_editor.player 加载玩家层级自定义变量视图。

        - 优先从关卡变量代码定义中按 `metadata["custom_variable_file"]` 引用的文件
          解析出一组代码级变量（只读视图，不写回 JSON）；
        - 其次加载 metadata.player_editor.player.custom_variables 中的非 chip_* 变量，
          作为模板级的额外自定义变量。
        """
        self.player_custom_variable_table.clear_fields()

        if not self.current_template_data:
            return

        schema_view = get_default_definition_schema_view()
        all_structs = schema_view.get_all_struct_definitions()
        struct_ids = sorted(all_structs.keys())
        self.player_custom_variable_table.set_struct_id_options(struct_ids)

        fields: List[Dict[str, Any]] = []

        # 1) 代码级关卡变量定义（只读视图，按 custom_variable_file 归属过滤）。
        external_payloads = self._get_external_player_level_variable_payloads()
        for payload in external_payloads:
            name_value = payload.get("variable_name") or payload.get("name")
            type_value = payload.get("variable_type")
            if not isinstance(name_value, str) or not isinstance(type_value, str):
                continue
            name_text = name_value.strip()
            type_text = type_value.strip()
            if not name_text or not type_text:
                continue
            value = payload.get("default_value")
            fields.append(
                {
                    "name": name_text,
                    "type_name": type_text,
                    "value": value,
                    "readonly": True,
                }
            )

        # 2) 玩家模板 JSON 中的额外自定义变量（非 chip_*，可编辑）。
        player_section = self.player_editor.player
        raw_variables = player_section.get("custom_variables")

        if isinstance(raw_variables, list):
            for entry in raw_variables:
                if not isinstance(entry, dict):
                    continue
                raw_name = entry.get("name")
                name = str(raw_name).strip() if isinstance(raw_name, str) else ""
                type_name = str(entry.get("variable_type", "")).strip()
                if not name or not type_name:
                    continue
                # chip_* 变量交由“自定义变量_局内存档变量”标签页管理
                if self._is_chip_variable_name(name):
                    continue
                value = entry.get("default_value")
                fields.append(
                    {
                        "name": name,
                        "type_name": type_name,
                        "value": value,
                    }
                )

        self.player_custom_variable_table.load_fields(fields)

    def _get_external_player_level_variable_payloads(self) -> List[Dict[str, Any]]:
        """按玩家模板 metadata.custom_variable_file 解析外部关卡变量定义列表。

        - 仅匹配“普通自定义变量”目录（`自定义变量/`），忽略 `自定义变量-局内存档变量/`；
        - 返回的列表元素为 LevelVariableSchemaView 聚合结果中的 payload 字典副本，
          仅用于 UI 层展示，不写回到玩家模板 JSON。
        """
        if not self.current_template_data:
            return []

        metadata_value = self.current_template_data.get("metadata") or {}
        if not isinstance(metadata_value, dict):
            return []

        raw_ref = metadata_value.get("custom_variable_file", "")
        if not isinstance(raw_ref, str):
            return []
        ref_text = raw_ref.strip()
        if not ref_text:
            return []

        normalized_ref = ref_text.replace("\\", "/")
        ref_stem = Path(normalized_ref).stem

        schema_view = get_default_level_variable_schema_view()
        all_variables = schema_view.get_all_variables()

        payloads: List[Dict[str, Any]] = []

        for payload in all_variables.values():
            if not isinstance(payload, dict):
                continue

            source_path_value = payload.get("source_path")
            source_stem_value = payload.get("source_stem")
            source_directory_value = payload.get("source_directory")

            # 仅关注普通自定义变量目录，过滤掉 `自定义变量-局内存档变量/` 等其他目录。
            if isinstance(source_directory_value, str):
                directory_text = source_directory_value.strip()
                if directory_text and directory_text != "自定义变量":
                    continue

            matched = False

            # 兼容旧写法：custom_variable_file 为完整相对路径
            if isinstance(source_path_value, str):
                candidate_path = source_path_value.replace("\\", "/").strip()
                if candidate_path and candidate_path == normalized_ref:
                    matched = True

            # 按 VARIABLE_FILE_ID 匹配（推荐写法）
            if not matched:
                variable_file_id = payload.get("variable_file_id")
                if isinstance(variable_file_id, str):
                    if variable_file_id.strip() == ref_text:
                        matched = True

            # 兼容写法：custom_variable_file 为文件名（不含扩展名），按 source_stem 匹配。
            if not matched and isinstance(source_stem_value, str):
                candidate_stem = source_stem_value.strip()
                if candidate_stem and candidate_stem == ref_stem:
                    matched = True

            if not matched:
                continue

            # 代码级 chip_* 存档镜像变量不在本标签页展示，交由“自定义变量_局内存档变量”管理。
            raw_var_name = payload.get("variable_name") or payload.get("name")
            if isinstance(raw_var_name, str):
                name_text = raw_var_name.strip()
                if name_text and self._is_chip_variable_name(name_text):
                    continue

            payloads.append(dict(payload))

        return payloads

    # ------------------------------------------------------------------ 局内存档绑定与 chip 变量

    def _get_ingame_save_selection_store_path(self) -> Optional[Path]:
        """返回记忆局内存档模板选择的本地状态文件路径。"""
        if self.resource_manager is None:
            return None
        workspace_path = getattr(self.resource_manager, "workspace_path", None)
        if not isinstance(workspace_path, Path):
            return None
        cache_directory = workspace_path / "app" / "runtime" / "cache"
        return cache_directory / "player_ingame_save_selection.json"

    def _load_last_selected_ingame_save_template(self) -> str:
        """读取当前玩家模板对应的上次选择的局内存档模板 ID。"""
        store_path = self._get_ingame_save_selection_store_path()
        if store_path is None or not store_path.exists():
            return ""

        serialized_text = store_path.read_text(encoding="utf-8")
        if not serialized_text.strip():
            return ""

        payload = json.loads(serialized_text)
        if not isinstance(payload, dict):
            return ""

        mapping_value = payload.get("player_template_last_selection")
        if not isinstance(mapping_value, dict):
            return ""

        current_template_id = getattr(self, "current_template_id", None)
        if not isinstance(current_template_id, str) or not current_template_id:
            return ""

        stored_value = mapping_value.get(current_template_id)
        if isinstance(stored_value, str):
            return stored_value.strip()
        return ""

    def _persist_ingame_save_selection(self, selected_template_id: str) -> None:
        """将当前玩家模板的局内存档模板选择写入本地状态文件。"""
        store_path = self._get_ingame_save_selection_store_path()
        current_template_id = getattr(self, "current_template_id", None)
        if store_path is None:
            return
        if not isinstance(current_template_id, str) or not current_template_id:
            return

        existing_payload: Dict[str, Any] = {}
        if store_path.exists():
            existing_text = store_path.read_text(encoding="utf-8")
            if existing_text.strip():
                loaded_payload = json.loads(existing_text)
                if isinstance(loaded_payload, dict):
                    existing_payload = loaded_payload

        selection_mapping = existing_payload.get("player_template_last_selection")
        if not isinstance(selection_mapping, dict):
            selection_mapping = {}

        if selected_template_id:
            selection_mapping[current_template_id] = selected_template_id
        else:
            if current_template_id in selection_mapping:
                selection_mapping.pop(current_template_id)

        existing_payload["player_template_last_selection"] = selection_mapping
        existing_payload["schema_version"] = 1

        store_path.parent.mkdir(parents=True, exist_ok=True)
        serialized_payload = json.dumps(
            existing_payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        store_path.write_text(serialized_payload, encoding="utf-8")

    def _load_player_ingame_save_binding(self, forced_template_id: Optional[str] = None) -> None:
        """加载局内存档模板绑定与 chip_* 变量视图。

        Args:
            forced_template_id: 当由下拉框选择触发时，显式指定要绑定的模板 ID；
                为 None 时按 metadata.player_editor.player.ingame_save.template_id
                或全局启用模板 active_template_id 推导。
        """
        if not hasattr(self, "player_ingame_save_template_combo") or not hasattr(
            self, "player_ingame_save_table"
        ):
            return

        self.player_ingame_save_table.clear_fields()
        self.player_ingame_save_table.setEnabled(False)

        if not self.current_template_data or self.resource_manager is None:
            self.player_ingame_save_template_combo.blockSignals(True)
            self.player_ingame_save_template_combo.clear()
            self.player_ingame_save_template_combo.blockSignals(False)
            self.player_ingame_save_summary_label.setText("当前工程未提供局内存档管理模板。")
            return

        save_points_config = self._get_save_points_config()
        templates_value = save_points_config.get("templates", [])
        if not isinstance(templates_value, list) or not templates_value:
            self.player_ingame_save_template_combo.blockSignals(True)
            self.player_ingame_save_template_combo.clear()
            self.player_ingame_save_template_combo.blockSignals(False)
            self.player_ingame_save_summary_label.setText("当前工程未配置任何局内存档管理模板。")
            return

        player_section = self.player_editor.player
        ingame_save_meta = player_section.get("ingame_save")
        if not isinstance(ingame_save_meta, dict):
            ingame_save_meta = {}
            player_section["ingame_save"] = ingame_save_meta

        enabled_flag = bool(save_points_config.get("enabled", False))
        active_template_id = str(save_points_config.get("active_template_id", "")).strip()
        previous_template_id = str(ingame_save_meta.get("template_id", "")).strip()
        last_selected_template_id = self._load_last_selected_ingame_save_template()

        if forced_template_id is not None:
            selected_template_id = forced_template_id.strip()
        else:
            selected_template_id = (
                previous_template_id
                or last_selected_template_id
                or (active_template_id if enabled_flag else "")
            )

        # 重建模板下拉列表
        self.player_ingame_save_template_combo.blockSignals(True)
        self.player_ingame_save_template_combo.clear()
        self.player_ingame_save_template_combo.addItem("（未选择）", "")

        template_map: Dict[str, Dict[str, Any]] = {}
        for template_payload in templates_value:
            if not isinstance(template_payload, dict):
                continue
            raw_template_id = template_payload.get("template_id", "")
            template_id = str(raw_template_id).strip()
            if not template_id:
                continue
            raw_name = template_payload.get("template_name")
            template_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
            display_name = template_name or template_id
            if template_name and template_name != template_id:
                label_text = f"{template_name} ({template_id})"
            else:
                label_text = display_name
            self.player_ingame_save_template_combo.addItem(label_text, template_id)
            template_map[template_id] = template_payload

        # 应用当前选择（如无显式绑定则回退到全局启用模板）
        if selected_template_id not in template_map:
            selected_template_id = ""

        if selected_template_id:
            index = self.player_ingame_save_template_combo.findData(selected_template_id)
            if index < 0:
                index = 0
        else:
            index = 0

        self.player_ingame_save_template_combo.setCurrentIndex(index)
        self.player_ingame_save_template_combo.setEnabled(True)
        self.player_ingame_save_template_combo.blockSignals(False)

        if not selected_template_id or selected_template_id not in template_map:
            self.player_ingame_save_summary_label.setText("未选择局内存档管理模板。")
            return

        selected_template = template_map[selected_template_id]
        self._persist_ingame_save_selection(selected_template_id)

        # 确保 metadata.player_editor.player.ingame_save.template_id 与当前选择一致
        if selected_template_id != previous_template_id:
            ingame_save_meta["template_id"] = selected_template_id
            player_section["ingame_save"] = ingame_save_meta
            # 仅在显式选择模板时（forced_template_id 非空字符串）视为用户触发的修改，
            # 避免在首次加载或仅切换页面时就触发保存。
            if forced_template_id is not None and forced_template_id.strip():
                self._mark_template_modified()
                self.data_changed.emit()

        # 根据局内存档模板 entries 构建 chip_* 变量表格字段（仅作为只读视图，不写回玩家模板 JSON）。
        # 同时整理每条映射的最大条目数，便于在概要标签中展示。
        chip_fields: List[Dict[str, Any]] = []
        chip_entry_summaries: List[Dict[str, Any]] = []
        entries_value = selected_template.get("entries", [])

        # 预先构造 struct_id -> 结构体名称 的映射，便于在概要中展示更友好的名称。
        struct_name_map: Dict[str, str] = {}
        schema_view = get_default_definition_schema_view()
        all_structs = schema_view.get_all_struct_definitions()
        for struct_id, payload in all_structs.items():
            if not isinstance(payload, dict):
                continue
            struct_type_value = payload.get("struct_ype")
            if not isinstance(struct_type_value, str):
                continue
            if struct_type_value.strip() != "ingame_save":
                continue
            raw_name = payload.get("name") or payload.get("struct_name") or struct_id
            display_name = str(raw_name)
            struct_name_map[str(struct_id)] = display_name

        if isinstance(entries_value, list):
            for index_in_list, entry_payload in enumerate(entries_value, start=1):
                if not isinstance(entry_payload, dict):
                    continue

                raw_index = entry_payload.get("index")
                if isinstance(raw_index, str) and raw_index.strip().isdigit():
                    struct_index = int(raw_index.strip())
                else:
                    struct_index = index_in_list

                struct_id_value = entry_payload.get("struct_id")
                struct_id_text = (
                    str(struct_id_value).strip() if isinstance(struct_id_value, str) else ""
                )

                max_length_value = entry_payload.get("max_length")
                max_length: int | None = None
                if isinstance(max_length_value, (int, float)):
                    max_length = int(max_length_value)
                elif isinstance(max_length_value, str) and max_length_value.strip().isdigit():
                    max_length = int(max_length_value.strip())

                variable_name = f"1_chip_{struct_index}"
                type_name_text = "结构体"
                value_object = struct_id_text
                effective_name = variable_name

                chip_fields.append(
                    {
                        "name": effective_name,
                        "type_name": type_name_text,
                        "value": value_object,
                        "readonly": True,
                    }
                )

                struct_display_name = struct_name_map.get(
                    struct_id_text, struct_id_text or "（未指定结构体）"
                )
                chip_entry_summaries.append(
                    {
                        "variable_name": variable_name,
                        "struct_name": struct_display_name,
                        "max_length": max_length,
                    }
                )

        if self.resource_manager is not None:
            struct_ids = self._load_ingame_save_struct_ids()
            self.player_ingame_save_table.set_struct_id_options(struct_ids)

        self.player_ingame_save_table.load_fields(chip_fields)
        self.player_ingame_save_table.setEnabled(True)
        self._update_player_ingame_save_table_height()

        template_name_text = str(selected_template.get("template_name", "")).strip() or selected_template_id

        summary_lines: List[str] = []
        summary_lines.append(
            f"当前模板：{template_name_text}（共 {len(chip_fields)} 条 chip 映射，变量名约定为 1_chip_序号）。"
        )

        if chip_entry_summaries:
            detail_parts: List[str] = []
            for entry_summary in chip_entry_summaries:
                variable_name = str(entry_summary.get("variable_name", ""))
                struct_name = str(entry_summary.get("struct_name", ""))
                max_length = entry_summary.get("max_length")
                if isinstance(max_length, int) and max_length > 0:
                    part_text = f"{variable_name} → {struct_name}: 最大 {max_length} 条"
                else:
                    part_text = f"{variable_name} → {struct_name}: 最大条目数不限"
                detail_parts.append(part_text)

            summary_lines.append("； ".join(detail_parts))

        self.player_ingame_save_summary_label.setText("\n".join(summary_lines))

    def _get_save_points_config(self) -> Dict[str, Any]:
        """从 GlobalResourceView 读取聚合后的局内存档管理配置。"""
        global_view = GlobalResourceView(self.resource_manager)
        management_data = global_view.management
        save_points_value = getattr(management_data, "save_points", {})
        if isinstance(save_points_value, dict):
            return save_points_value
        return {}

    def _load_ingame_save_struct_ids(self) -> List[str]:
        """加载 struct_ype == \"ingame_save\" 的结构体 ID 列表。"""
        struct_ids: List[str] = []
        schema_view = get_default_definition_schema_view()
        all_structs = schema_view.get_all_struct_definitions()

        for struct_id, payload in all_structs.items():
            if not isinstance(payload, dict):
                continue
            struct_type_value = payload.get("struct_ype")
            if not isinstance(struct_type_value, str):
                continue
            if struct_type_value.strip() != "ingame_save":
                continue
            struct_ids.append(str(struct_id))
        return struct_ids

    @staticmethod
    def _is_chip_variable_name(variable_name: str) -> bool:
        """判断变量名是否符合 N_chip_M 约定格式。"""
        text = variable_name.strip()
        if "_chip_" not in text:
            return False
        prefix, suffix = text.split("_chip_", 1)
        if not prefix or not suffix:
            return False
        if not prefix.isdigit() or not suffix.isdigit():
            return False
        return True

    def _update_player_ingame_save_table_height(self) -> None:
        """根据当前行数与行高调整局内存档变量表格高度，使其随内容自然增减。"""
        if not hasattr(self, "player_ingame_save_table"):
            return
        table = self.player_ingame_save_table.table
        if table is None:
            return

        row_count = table.rowCount()
        vertical_header = table.verticalHeader()
        if vertical_header is not None and row_count > 0:
            row_height = vertical_header.sectionSize(0)
        else:
            row_height = Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL

        horizontal_header = table.horizontalHeader()
        header_height = horizontal_header.height() if horizontal_header is not None else 0

        frame_height = table.frameWidth() * 2
        effective_rows = max(1, row_count)
        content_height = row_height * effective_rows
        extra_padding = Sizes.PADDING_SMALL

        total_height = header_height + frame_height + content_height + extra_padding
        table.setMinimumHeight(total_height)
        table.setMaximumHeight(total_height)

    def _on_player_graphs_tab_changed(self) -> None:
        """玩家层级节点图变更时写回 metadata.player_editor.player."""
        if not self.current_template_data or not self.player_graphs_context:
            return
        player_section = self.player_editor.player
        player_section["graphs"] = self.player_graphs_context.default_graphs
        if self.player_graphs_context.graph_variable_overrides:
            player_section["graph_variable_overrides"] = (
                self.player_graphs_context.graph_variable_overrides
            )
        else:
            player_section.pop("graph_variable_overrides", None)
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_role_graphs_tab_changed(self) -> None:
        """角色层级节点图变更时写回 metadata.player_editor.role."""
        if not self.current_template_data or not self.role_graphs_context:
            return
        role_section = self.player_editor.role
        role_section["graphs"] = self.role_graphs_context.default_graphs
        if self.role_graphs_context.graph_variable_overrides:
            role_section["graph_variable_overrides"] = (
                self.role_graphs_context.graph_variable_overrides
            )
        else:
            role_section.pop("graph_variable_overrides", None)
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_all_players_changed(self, state: int) -> None:
        if not self.current_template_data:
            return
        is_checked = state == QtCore.Qt.CheckState.Checked.value
        self.player_editor.player["all_players"] = is_checked

        # 如果选中全部玩家，则取消其他选项
        if is_checked:
            for checkbox in self.player_selection_checkboxes:
                checkbox.blockSignals(True)
                checkbox.setChecked(False)
                checkbox.blockSignals(False)
            self.player_editor.player["selected_players"] = []

        self._mark_template_modified()
        self.data_changed.emit()

    def _on_player_selection_changed(self, state: int) -> None:  # noqa: ARG002
        if not self.current_template_data:
            return

        selected_players: List[int] = []
        for checkbox in self.player_selection_checkboxes:
            if checkbox.isChecked():
                player_index = checkbox.property("player_index")
                selected_players.append(player_index)

        # 如果选择了具体玩家，则取消"全部玩家"选项
        if selected_players:
            self.all_players_checkbox.blockSignals(True)
            self.all_players_checkbox.setChecked(False)
            self.all_players_checkbox.blockSignals(False)
            self.player_editor.player["all_players"] = False

        self.player_editor.player["selected_players"] = selected_players
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_level_changed(self, value: int) -> None:
        if not self.current_template_data:
            return
        self.current_template_data["level"] = int(value)
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_spawn_point_changed(self, text: str) -> None:
        if not self.current_template_data:
            return
        self.player_editor.player["spawn_point"] = text.strip()
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_profession_changed(self, text: str) -> None:
        if not self.current_template_data:
            return
        self.current_template_data["default_profession_id"] = text.strip()
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_allow_resurrection_changed(self, state: int) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["allow_resurrection"] = state == QtCore.Qt.CheckState.Checked.value
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_show_resurrection_ui_changed(self, state: int) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["show_ui"] = state == QtCore.Qt.CheckState.Checked.value
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_resurrection_time_changed(self, value: float) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["time"] = float(value)
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_auto_resurrection_changed(self, state: int) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["auto_resurrection"] = state == QtCore.Qt.CheckState.Checked.value
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_resurrection_count_limit_changed(self, state: int) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["count_limit"] = state == QtCore.Qt.CheckState.Checked.value
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_resurrection_count_changed(self, value: int) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["count"] = int(value)
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_resurrection_points_changed(self) -> None:
        if not self.current_template_data:
            return
        text = self.resurrection_points_edit.toPlainText()
        points = [line.strip() for line in text.split("\n") if line.strip()]
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["points"] = points
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_resurrection_point_rule_changed(self, index: int) -> None:
        if not self.current_template_data:
            return
        rule_mapping = {
            0: "nearest",
            1: "latest_activated",
            2: "highest_priority",
            3: "random",
        }
        rule = rule_mapping.get(index, "nearest")
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["point_rule"] = rule
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_resurrection_health_ratio_changed(self, value: float) -> None:
        if not self.current_template_data:
            return
        resurrection_data = self.player_editor.player.setdefault("resurrection", {})
        resurrection_data["health_ratio"] = float(value)
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_special_knockout_changed(self, value: float) -> None:
        if not self.current_template_data:
            return
        self.player_editor.player["special_knockout_pct"] = float(value)
        self._mark_template_modified()
        self.data_changed.emit()

    # ------------------------------------------------------------------ 角色编辑数据加载/写回

    def _load_role_fields(self) -> None:
        role = self.player_editor.role

        self.role_play_own_sound_switch.blockSignals(True)
        self.role_play_own_sound_switch.setChecked(bool(role.get("play_own_sound", False)))
        self.role_play_own_sound_switch.blockSignals(False)

        self.role_attributes_edit.blockSignals(True)
        self.role_attributes_edit.setPlainText(str(role.get("attributes_text", "")).strip())
        self.role_attributes_edit.blockSignals(False)

        combat_settings_data = role.get("combat_settings")
        if self.role_combat_settings_section is not None:
            self.role_combat_settings_section.set_from_metadata(combat_settings_data)

        # 加载角色层级自定义变量
        self._load_role_custom_variables()

    # --- 角色字段写回 ---------------------------------------------------------

    def _on_role_play_own_sound_changed(self, checked: bool) -> None:
        if not self.current_template_data:
            return
        role = self.player_editor.role
        role["play_own_sound"] = bool(checked)
        role["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_role_attributes_changed(self) -> None:
        if not self.current_template_data:
            return
        role = self.player_editor.role
        role["attributes_text"] = self.role_attributes_edit.toPlainText()
        role["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_role_combat_settings_changed(self) -> None:
        if not self.current_template_data or self.role_combat_settings_section is None:
            return
        role = self.player_editor.role
        combat_settings_data = self.role_combat_settings_section.to_metadata()
        role["combat_settings"] = combat_settings_data
        role["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._mark_template_modified()
        self.data_changed.emit()

    def _load_role_custom_variables(self) -> None:
        """根据 metadata.player_editor.role 加载角色层级自定义变量。"""
        self.role_custom_variable_table.clear_fields()

        if not self.current_template_data:
            return

        schema_view = get_default_definition_schema_view()
        all_structs = schema_view.get_all_struct_definitions()
        struct_ids = sorted(all_structs.keys())
        self.role_custom_variable_table.set_struct_id_options(struct_ids)

        role_section = self.player_editor.role
        raw_variables = role_section.get("custom_variables")
        fields: List[Dict[str, Any]] = []

        if isinstance(raw_variables, list):
            for entry in raw_variables:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", "")).strip()
                type_name = str(entry.get("variable_type", "")).strip()
                if not name or not type_name:
                    continue
                value = entry.get("default_value")
                fields.append(
                    {
                        "name": name,
                        "type_name": type_name,
                        "value": value,
                    }
                )

        self.role_custom_variable_table.load_fields(fields)

    def _add_player_custom_variable(self) -> None:
        """玩家层级：添加一条新的自定义变量记录。"""
        if not self.current_template_data:
            return

        existing_fields = self.player_custom_variable_table.get_all_fields()
        existing_names: List[str] = []
        for field in existing_fields:
            name = str(field.get("name", "")).strip()
            if name:
                existing_names.append(name)
        variable_name = generate_unique_name("新变量", existing_names)

        supported_types = get_all_variable_types()
        default_type = supported_types[0] if supported_types else "字符串"

        self.player_custom_variable_table.add_field_row(
            name=variable_name,
            type_name=default_type,
            value="",
        )

        # 选中新添加的字段主行
        table = self.player_custom_variable_table.table
        last_main_row = table.rowCount() - 2
        if last_main_row >= 0:
            table.selectRow(last_main_row)
            table.setFocus()

    def _remove_player_custom_variable(self) -> None:
        """玩家层级：删除当前选中的自定义变量。"""
        if not self.current_template_data:
            return

        table = self.player_custom_variable_table.table
        current_row = table.currentRow()
        if current_row < 0:
            current_row = table.rowCount() - 2
        if current_row < 0:
            return

        self.player_custom_variable_table.remove_field_at_row(current_row)

    def _add_role_custom_variable(self) -> None:
        """角色层级：添加一条新的自定义变量记录。"""
        if not self.current_template_data:
            return

        existing_fields = self.role_custom_variable_table.get_all_fields()
        existing_names: List[str] = []
        for field in existing_fields:
            name = str(field.get("name", "")).strip()
            if name:
                existing_names.append(name)
        variable_name = generate_unique_name("新变量", existing_names)

        supported_types = get_all_variable_types()
        default_type = supported_types[0] if supported_types else "字符串"

        self.role_custom_variable_table.add_field_row(
            name=variable_name,
            type_name=default_type,
            value="",
        )

        table = self.role_custom_variable_table.table
        last_main_row = table.rowCount() - 2
        if last_main_row >= 0:
            table.selectRow(last_main_row)
            table.setFocus()

    def _remove_role_custom_variable(self) -> None:
        """角色层级：删除当前选中的自定义变量。"""
        if not self.current_template_data:
            return

        table = self.role_custom_variable_table.table
        current_row = table.currentRow()
        if current_row < 0:
            current_row = table.rowCount() - 2
        if current_row < 0:
            return

        self.role_custom_variable_table.remove_field_at_row(current_row)

    def _on_player_custom_variables_changed(self) -> None:
        """玩家层级自定义变量变更时写回 metadata.player_editor.player."""
        if not self.current_template_data:
            return

        player_section = self.player_editor.player

        # 外部关卡变量定义仅作为只读视图存在，不写回到玩家模板 JSON。
        external_names: List[str] = []
        for payload in self._get_external_player_level_variable_payloads():
            name_value = payload.get("variable_name") or payload.get("name")
            if isinstance(name_value, str):
                name_text = name_value.strip()
                if name_text:
                    external_names.append(name_text)
        external_name_set = set(external_names)

        # 普通自定义变量标签页仅负责非 chip_* 变量
        fields = self.player_custom_variable_table.get_all_fields()
        normal_variables: List[Dict[str, Any]] = []
        for field in fields:
            name = str(field.get("name", "")).strip()
            type_name = str(field.get("type_name", "")).strip()
            if not name or not type_name:
                continue
            # 外部关卡变量定义仅用于只读展示，不写入 custom_variables。
            if name in external_name_set:
                continue
            if self._is_chip_variable_name(name):
                # chip_* 变量交由局内存档标签页管理
                continue
            value = field.get("value")
            normal_variables.append(
                {
                    "name": name,
                    "variable_type": type_name,
                    "default_value": value,
                    "description": "",
                }
            )

        # 保留既有 chip_* 变量
        raw_existing = player_section.get("custom_variables")
        chip_variables: List[Dict[str, Any]] = []
        if isinstance(raw_existing, list):
            for entry in raw_existing:
                if not isinstance(entry, dict):
                    continue
                raw_name = entry.get("name")
                variable_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
                if self._is_chip_variable_name(variable_name):
                    chip_variables.append(entry)

        player_section["custom_variables"] = normal_variables + chip_variables
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_player_ingame_save_template_changed(self, index: int) -> None:
        """局内存档模板下拉变化时，刷新绑定与 chip_* 变量视图。"""
        if not self.current_template_data:
            return
        if not hasattr(self, "player_ingame_save_template_combo"):
            return

        combo = self.player_ingame_save_template_combo
        if index < 0 or index >= combo.count():
            return

        data = combo.itemData(index)
        if isinstance(data, str):
            selected_template_id = data.strip()
        else:
            selected_template_id = combo.itemText(index).strip()

        self._persist_ingame_save_selection(selected_template_id)
        # 直接复用加载逻辑，根据当前下拉选择重新构建绑定与表格
        self._load_player_ingame_save_binding(selected_template_id or None)

    def _on_player_ingame_save_variables_changed(self) -> None:
        """局内存档 chip_* 变量表格变更时写回 metadata.player_editor.player.custom_variables。"""
        if not self.current_template_data:
            return
        player_section = self.player_editor.player

        fields = self.player_ingame_save_table.get_all_fields()
        chip_variables_by_name: Dict[str, Dict[str, Any]] = {}
        for field in fields:
            name = str(field.get("name", "")).strip()
            type_name = str(field.get("type_name", "")).strip()
            if not name or not type_name:
                continue
            if not self._is_chip_variable_name(name):
                continue
            value = field.get("value")
            chip_variables_by_name[name] = {
                "name": name,
                "variable_type": type_name,
                "default_value": value,
                "description": "",
            }

        # 先保留所有非 chip_* 变量，再追加最新的 chip_* 变量
        raw_existing = player_section.get("custom_variables")
        normal_variables: List[Dict[str, Any]] = []
        if isinstance(raw_existing, list):
            for entry in raw_existing:
                if not isinstance(entry, dict):
                    continue
                raw_name = entry.get("name")
                variable_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
                if self._is_chip_variable_name(variable_name):
                    continue
                normal_variables.append(entry)

        merged_variables: List[Dict[str, Any]] = normal_variables + list(
            chip_variables_by_name.values()
        )
        player_section["custom_variables"] = merged_variables

        self._mark_template_modified()
        self.data_changed.emit()
        self._update_player_ingame_save_table_height()

    def _on_role_custom_variables_changed(self) -> None:
        """角色层级自定义变量变更时写回 metadata.player_editor.role."""
        if not self.current_template_data:
            return

        fields = self.role_custom_variable_table.get_all_fields()
        variables: List[Dict[str, Any]] = []
        for field in fields:
            name = str(field.get("name", "")).strip()
            type_name = str(field.get("type_name", "")).strip()
            if not name or not type_name:
                continue
            value = field.get("value")
            variables.append(
                {
                    "name": name,
                    "variable_type": type_name,
                    "default_value": value,
                    "description": "",
                }
            )

        self.player_editor.role["custom_variables"] = variables
        self.player_editor.role["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._mark_template_modified()
        self.data_changed.emit()

    def _on_struct_view_requested(self, struct_id: str) -> None:
        """处理查看结构体请求，弹出只读结构体查看对话框。"""
        if not struct_id:
            return

        # 从定义视图获取结构体详情
        schema_view = get_default_definition_schema_view()
        all_structs = schema_view.get_all_struct_definitions()
        struct_payload = all_structs.get(struct_id)

        # 弹出只读结构体查看对话框
        dialog = StructViewerDialog(
            struct_id=struct_id,
            struct_payload=struct_payload,
            parent=self,  # type: ignore[arg-type]
        )
        dialog.exec()


