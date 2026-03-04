"""
graph_id: server_composite_merged_pins_example_01
graph_name: 模板示例_合并引脚_复合节点用法
graph_type: server
description: 示例节点图（复合节点：合并引脚/扇出映射）：外部一个数据入引脚在复合子图内部同时驱动多个节点输入，用于验证导出 .gia 的 InterfaceMapping 与引脚稳定性
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

from 资源库.项目存档.示例项目模板.复合节点库.composite_合并引脚_示例_类格式 import 合并引脚_示例_类格式


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_合并引脚结果A",
        variable_type="整数",
        default_value=0,
        description="合并引脚复合节点输出结果 A。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_合并引脚结果B",
        variable_type="整数",
        default_value=0,
        description="合并引脚复合节点输出结果 B。",
        is_exposed=False,
    ),
]


class 模板示例_合并引脚_复合节点用法:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.合并引脚_示例_类格式 = 合并引脚_示例_类格式(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        结果A, 结果B = self.合并引脚_示例_类格式.合并整数输入(
            共享整数=10,
            加数A=1,
            加数B=2,
        )

        设置节点图变量(self.game, 变量名="调试_合并引脚结果A", 变量值=结果A, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_合并引脚结果B", 变量值=结果B, 是否触发事件=False)

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

