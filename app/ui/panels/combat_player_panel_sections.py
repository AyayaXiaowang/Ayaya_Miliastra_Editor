"""
CombatPlayerEditorPanel 辅助模块（拆分入口）。

历史上本模块承载了大量“UI 构建 + 字段加载/写回 + 节点图上下文 + 自定义变量 + 局内存档绑定”等逻辑，
导致单文件体积过大、维护成本高。

现在将实现按职责拆分到多个 mixin 文件中，本文件仅作为稳定的对外导出入口：
- 保持 `from ui.panels.combat_player_panel_sections import CombatPlayerPanelSectionsMixin` 不变
- 继续对外导出 `_PlayerEditorStruct` / `_GraphBindingContext` 供其他面板复用
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6 import QtWidgets

from app.ui.foundation.toggle_switch import ToggleSwitch
from app.ui.panels.combat_ability_components import CombatSettingsSection
from app.ui.panels.template_instance.graphs_tab import GraphsTab
from app.ui.panels.combat_player_panel_sections_custom_variables import (
    CombatPlayerPanelSectionsCustomVariablesMixin,
)
from app.ui.panels.combat_player_panel_sections_graphs import CombatPlayerPanelSectionsGraphsMixin
from app.ui.panels.combat_player_panel_sections_ingame_save import CombatPlayerPanelSectionsIngameSaveMixin
from app.ui.panels.combat_player_panel_sections_player_fields import (
    CombatPlayerPanelSectionsPlayerFieldsMixin,
)
from app.ui.panels.combat_player_panel_sections_role_fields import CombatPlayerPanelSectionsRoleFieldsMixin
from app.ui.panels.combat_player_panel_sections_types import _GraphBindingContext, _PlayerEditorStruct
from app.ui.panels.combat_player_panel_sections_ui import CombatPlayerPanelSectionsUIMixin
from app.ui.widgets.two_row_field_table_widget import TwoRowFieldTableWidget

__all__ = [
    "CombatPlayerPanelSectionsMixin",
    "_GraphBindingContext",
    "_PlayerEditorStruct",
]


class CombatPlayerPanelSectionsMixin(
    CombatPlayerPanelSectionsUIMixin,
    CombatPlayerPanelSectionsGraphsMixin,
    CombatPlayerPanelSectionsIngameSaveMixin,
    CombatPlayerPanelSectionsCustomVariablesMixin,
    CombatPlayerPanelSectionsPlayerFieldsMixin,
    CombatPlayerPanelSectionsRoleFieldsMixin,
):
    """CombatPlayerEditorPanel 的 UI 构建与字段绑定逻辑（拆分聚合类）。"""

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


