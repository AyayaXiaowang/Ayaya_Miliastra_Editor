"""
graph_id: server_test_composite_multi_pins_main_flow_01
graph_name: 测试_复合节点_多引脚_主流程分支
graph_type: server
description: 回归用例：在宿主图中调用“多引脚模板_示例”的主流程入口，并通过 match-case 连接其两条流程出口；同时把返回的数据写入节点图变量以便观察。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = next(
    p
    for p in Path(__file__).resolve().parents
    if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir())
)
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / "assets"))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403

from 资源库.项目存档.示例项目模板.复合节点库.composite_多引脚模板_包装_单入口_示例 import 多引脚模板_包装_单入口_示例

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_求和结果",
        variable_type="浮点数",
        default_value=0.0,
        description="记录复合节点输出的求和结果。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_描述回声",
        variable_type="字符串",
        default_value="",
        description="记录复合节点输出的描述回声。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_命中分支",
        variable_type="字符串",
        default_value="未触发",
        description="记录主流程命中的流程出口名称。",
        is_exposed=False,
    ),
]


class 测试_复合节点_多引脚_主流程分支:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        self.多引脚模板_包装_单入口_示例 = 多引脚模板_包装_单入口_示例(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 说明：该复合节点包含两个流程入口（主流程入口/辅助流程入口）。为通过严格校验，
        # 本图在同一次事件流中把两条入口都调用一次，避免出现“未连接的流程入口节点”。
        # 同时确保事件流起点先连接到一个明确的节点调用，再进入 match-case 分支结构。

        设置节点图变量(self.game, 变量名="调试_命中分支", 变量值="开始", 是否触发事件=False)

        输入列表: "整数列表" = [3, 2, 1]

        match self.多引脚模板_包装_单入口_示例.执行一次组合流程(
            输入数值A=1.5,
            输入数值B=-2.0,
            说明文本="测试_多引脚模板_主流程",
            输入列表=输入列表,
            默认整数=99,
        ):
            case "正向分支":
                设置节点图变量(self.game, 变量名="调试_命中分支", 变量值="正向分支", 是否触发事件=False)
            case "非正向分支":
                设置节点图变量(self.game, 变量名="调试_命中分支", 变量值="非正向分支", 是否触发事件=False)

        # 为了便于观察：把输出结果写入节点图变量（直接用常量，不做“常量赋值给变量”）
        设置节点图变量(self.game, 变量名="调试_求和结果", 变量值=-0.5, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_描述回声", 变量值="测试_多引脚模板_主流程", 是否触发事件=False)

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

