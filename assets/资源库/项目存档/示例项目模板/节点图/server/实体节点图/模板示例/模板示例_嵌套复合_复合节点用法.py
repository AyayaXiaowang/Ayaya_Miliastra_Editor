"""
graph_id: server_composite_nested_example_01
graph_name: 模板示例_嵌套复合_复合节点用法
graph_type: server
description: 示例节点图（复合节点套复合节点）：调用“嵌套复合_示例_类格式”，覆盖导出 .gia 时递归打包复合节点定义（外层+内层）与内部引脚映射稳定性。
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
        name="调试_嵌套复合_最近分支标签",
        variable_type="字符串",
        default_value="未触发",
        description="最近一次调用嵌套复合节点时命中的流程分支标签（分支为0/分支为1/分支为其他）。",
        is_exposed=False,
    ),
]


class 模板示例_嵌套复合_复合节点用法:
    """宿主图调用“嵌套复合_示例_类格式”，验证嵌套复合节点导出链路。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        self.嵌套复合_示例_类格式 = 嵌套复合_示例_类格式(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        分支值: "整数" = random.randint(0, 3)

        match self.嵌套复合_示例_类格式.组合执行并分支(
            分支值=分支值,
            输入数值A=2.0,
            输入数值B=0.5,
            说明文本="嵌套复合节点导出测试",
        ):
            case "分支为0":
                设置节点图变量(
                    self.game,
                    变量名="调试_嵌套复合_最近分支标签",
                    变量值="分支为0",
                    是否触发事件=False,
                )
            case "分支为1":
                设置节点图变量(
                    self.game,
                    变量名="调试_嵌套复合_最近分支标签",
                    变量值="分支为1",
                    是否触发事件=False,
                )
            case "分支为其他":
                设置节点图变量(
                    self.game,
                    变量名="调试_嵌套复合_最近分支标签",
                    变量值="分支为其他",
                    是否触发事件=False,
                )

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

