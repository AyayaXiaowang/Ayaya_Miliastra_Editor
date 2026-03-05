from __future__ import annotations

from engine.graph.models.package_model import LevelVariableDefinition


VARIABLE_FILE_ID = "test_project_ui_text_placeholders"
VARIABLE_FILE_NAME = "测试项目_UI文本占位符变量"


LEVEL_VARIABLES: list[LevelVariableDefinition] = [
    LevelVariableDefinition(
        variable_id="var_ui_text_level_name",
        variable_name="level_name",
        variable_type="字符串",
        default_value="",
        is_global=False,
        description="UI 文本占位符：{{ls.level_name}}",
        metadata={"category": "UI"},
    ),
    LevelVariableDefinition(
        variable_id="var_ui_text_author_name",
        variable_name="author_name",
        variable_type="字符串",
        default_value="",
        is_global=False,
        description="UI 文本占位符：{{ls.author_name}}",
        metadata={"category": "UI"},
    ),
    # 关卡选择页投票数（每个关卡一个数字胶囊）：{{ls.level_XX_online_count}}
    LevelVariableDefinition(
        variable_id="var_ui_text_lv01_online_cnt",
        variable_name="lv01_online_cnt",
        variable_type="整数",
        default_value=0,
        is_global=False,
        description="UI 文本占位符：{{ls.lv01_online_cnt}}（关卡01投票数，0~4）",
        metadata={"category": "UI"},
    ),
    LevelVariableDefinition(
        variable_id="var_ui_text_lv02_online_cnt",
        variable_name="lv02_online_cnt",
        variable_type="整数",
        default_value=0,
        is_global=False,
        description="UI 文本占位符：{{ls.lv02_online_cnt}}（关卡02投票数，0~4）",
        metadata={"category": "UI"},
    ),
    LevelVariableDefinition(
        variable_id="var_ui_text_lv03_online_cnt",
        variable_name="lv03_online_cnt",
        variable_type="整数",
        default_value=0,
        is_global=False,
        description="UI 文本占位符：{{ls.lv03_online_cnt}}（关卡03投票数，0~4）",
        metadata={"category": "UI"},
    ),
    LevelVariableDefinition(
        variable_id="var_ui_text_lv04_online_cnt",
        variable_name="lv04_online_cnt",
        variable_type="整数",
        default_value=0,
        is_global=False,
        description="UI 文本占位符：{{ls.lv04_online_cnt}}（关卡04投票数，0~4）",
        metadata={"category": "UI"},
    ),
    LevelVariableDefinition(
        variable_id="var_ui_text_lv05_online_cnt",
        variable_name="lv05_online_cnt",
        variable_type="整数",
        default_value=0,
        is_global=False,
        description="UI 文本占位符：{{ls.lv05_online_cnt}}（关卡05投票数，0~4）",
        metadata={"category": "UI"},
    ),
    LevelVariableDefinition(
        variable_id="var_ui_text_lv06_online_cnt",
        variable_name="lv06_online_cnt",
        variable_type="整数",
        default_value=0,
        is_global=False,
        description="UI 文本占位符：{{ls.lv06_online_cnt}}（关卡06投票数，0~4）",
        metadata={"category": "UI"},
    ),
    LevelVariableDefinition(
        variable_id="var_ui_text_lv07_online_cnt",
        variable_name="lv07_online_cnt",
        variable_type="整数",
        default_value=0,
        is_global=False,
        description="UI 文本占位符：{{ls.lv07_online_cnt}}（关卡07投票数，0~4）",
        metadata={"category": "UI"},
    ),
    LevelVariableDefinition(
        variable_id="var_ui_text_lv08_online_cnt",
        variable_name="lv08_online_cnt",
        variable_type="整数",
        default_value=0,
        is_global=False,
        description="UI 文本占位符：{{ls.lv08_online_cnt}}（关卡08投票数，0~4）",
        metadata={"category": "UI"},
    ),
    LevelVariableDefinition(
        variable_id="var_ui_text_lv09_online_cnt",
        variable_name="lv09_online_cnt",
        variable_type="整数",
        default_value=0,
        is_global=False,
        description="UI 文本占位符：{{ls.lv09_online_cnt}}（关卡09投票数，0~4）",
        metadata={"category": "UI"},
    ),
    LevelVariableDefinition(
        variable_id="var_ui_text_lv10_online_cnt",
        variable_name="lv10_online_cnt",
        variable_type="整数",
        default_value=0,
        is_global=False,
        description="UI 文本占位符：{{ls.lv10_online_cnt}}（关卡10投票数，0~4）",
        metadata={"category": "UI"},
    ),
]

