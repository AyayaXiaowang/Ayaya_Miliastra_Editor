from __future__ import annotations

from engine.graph.models.package_model import LevelVariableDefinition

VARIABLE_FILE_ID = "test_project_player_custom_variables_ui_01"
VARIABLE_FILE_NAME = "测试项目_UI交互按钮_装备配置ID变量"

# 说明：
# - 用于 UI 导入链路给“可交互道具展示按钮”提供一个统一的“装备配置ID变量”占位载体。
# - 不要求该配置ID真实对应某个道具；默认值 0 即可。
LEVEL_VARIABLES: list[LevelVariableDefinition] = [
    LevelVariableDefinition(
        variable_id="var_player_ui_button_equip_config_id",
        variable_name="UI_交互按钮_装备配置ID",
        variable_type="配置ID",
        default_value=0,
        is_global=False,
        description="UI 可交互按钮锚点的统一配置ID占位变量（所有按钮共用，默认 0）。",
        metadata={"category": "UI"},
    ),
]

