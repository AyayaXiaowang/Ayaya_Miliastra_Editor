from __future__ import annotations

from engine.resources.auto_custom_variable_registry import AutoCustomVariableDeclaration

# 测试项目：自定义变量注册表（测试夹具最小集）。
CUSTOM_VARIABLE_DECLARATIONS: list[AutoCustomVariableDeclaration] = [
    AutoCustomVariableDeclaration(
        variable_id="var_test_workbench_catalog_player_string",
        variable_name="测试_PS_变量浏览器_字符串",
        variable_type="字符串",
        default_value="测试默认值",
        description="测试夹具：Workbench 变量清单冒烟用。",
        owner="player",
        category="测试夹具",
    ),
]

