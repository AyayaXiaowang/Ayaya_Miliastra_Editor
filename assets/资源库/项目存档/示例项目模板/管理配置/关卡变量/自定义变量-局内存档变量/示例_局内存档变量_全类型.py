from __future__ import annotations

from engine.graph.models.package_model import LevelVariableDefinition


VARIABLE_FILE_ID = "sample_ingame_save_variables_all_types"
VARIABLE_FILE_NAME = "示例_局内存档变量_全类型"


LEVEL_VARIABLES: list[LevelVariableDefinition] = [
    LevelVariableDefinition(
        variable_id="var_sample_player_1_chip_1",
        variable_name="1_chip_1",
        variable_type="结构体",
        default_value="玩家存档",
        is_global=False,
        description="示例：玩家存档（基础进度与元信息）",
        metadata={"category": "教学示例"},
    ),
    LevelVariableDefinition(
        variable_id="var_sample_player_1_chip_2",
        variable_name="1_chip_2",
        variable_type="结构体",
        default_value="玩家资源与货币",
        is_global=False,
        description="示例：玩家资源与货币（钻石/金币/碎片等）",
        metadata={"category": "教学示例"},
    ),
    LevelVariableDefinition(
        variable_id="var_sample_player_1_chip_3",
        variable_name="1_chip_3",
        variable_type="结构体",
        default_value="玩家背包",
        is_global=False,
        description="示例：玩家背包（武器/物品条目等）",
        metadata={"category": "教学示例"},
    ),
    LevelVariableDefinition(
        variable_id="var_sample_player_1_chip_4",
        variable_name="1_chip_4",
        variable_type="结构体",
        default_value="玩家锻造状态",
        is_global=False,
        description="示例：玩家锻造状态（计数器/保底等）",
        metadata={"category": "教学示例"},
    ),
    LevelVariableDefinition(
        variable_id="var_sample_player_1_chip_5",
        variable_name="1_chip_5",
        variable_type="结构体",
        default_value="武器条目",
        is_global=False,
        description="示例：武器条目（每条一把武器；引擎内部以 StructList 存储）",
        metadata={"category": "教学示例"},
    ),
    LevelVariableDefinition(
        variable_id="var_sample_player_1_chip_6",
        variable_name="1_chip_6",
        variable_type="结构体",
        default_value="BOSS条目",
        is_global=False,
        description="示例：BOSS条目（每条一个BOSS状态；引擎内部以 StructList 存储）",
        metadata={"category": "教学示例"},
    ),
]


