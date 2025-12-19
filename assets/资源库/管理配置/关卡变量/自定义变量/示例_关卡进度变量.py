from __future__ import annotations

from engine.graph.models.package_model import LevelVariableDefinition


VARIABLE_FILE_ID = "sample_level_progress_variables"
VARIABLE_FILE_NAME = "示例_关卡进度变量"


LEVEL_VARIABLES: list[LevelVariableDefinition] = [
    LevelVariableDefinition(
        variable_id="var_sample_level1_passed",
        variable_name="关卡1已通过",
        variable_type="布尔值",
        default_value=False,
        is_global=False,
        description="示例：玩家是否已通过关卡1（踏板开关触发双开门后写入 True）。",
        metadata={"category": "教学示例"},
    ),
]


