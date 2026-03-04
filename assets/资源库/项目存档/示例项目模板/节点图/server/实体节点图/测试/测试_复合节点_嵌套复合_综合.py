"""
graph_id: server_test_composite_nested_composite_01
graph_name: 测试_复合节点_嵌套复合_综合
graph_type: server
description: 回归用例：宿主图调用“嵌套复合_示例_类格式”（复合节点内部再调用其它复合节点），并将其三个流程出口分别接到不同的后续写回；用于验证“复合节点套复合节点”的导出与映射。
"""

from __future__ import annotations

import sys
import random
from pathlib import Path

PROJECT_ROOT = next(
    p
    for p in Path(__file__).resolve().parents
    if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir())
)
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / "assets"))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403

from 资源库.项目存档.示例项目模板.复合节点库.composite_嵌套复合_示例_类格式 import 嵌套复合_示例_类格式

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_命中分支",
        variable_type="字符串",
        default_value="未触发",
        description="记录嵌套复合节点命中的流程出口。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_分支值",
        variable_type="整数",
        default_value=0,
        description="最近一次传入嵌套复合节点的分支值。",
        is_exposed=False,
    ),
]


class 测试_复合节点_嵌套复合_综合:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        self.嵌套复合_示例_类格式 = 嵌套复合_示例_类格式(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        分支值: "整数" = random.randint(0, 3)
        设置节点图变量(self.game, 变量名="调试_分支值", 变量值=分支值, 是否触发事件=False)

        match self.嵌套复合_示例_类格式.组合执行并分支(
            分支值=分支值,
            输入数值A=2.0,
            输入数值B=3.0,
            说明文本="测试_嵌套复合",
        ):
            case "分支为0":
                设置节点图变量(self.game, 变量名="调试_命中分支", 变量值="分支为0", 是否触发事件=False)
            case "分支为1":
                设置节点图变量(self.game, 变量名="调试_命中分支", 变量值="分支为1", 是否触发事件=False)
            case "分支为其他":
                设置节点图变量(self.game, 变量名="调试_命中分支", 变量值="分支为其他", 是否触发事件=False)

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

