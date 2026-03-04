"""
graph_id: server_composite_empty_example_01
graph_name: 模板示例_空复合节点_复合节点用法
graph_type: server
description: 示例节点图（复合节点：空复合）：只有流程入/流程出的最小复合节点，用于验证导出 .gia 的最小流程引脚集合与稳定性
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

from 资源库.项目存档.示例项目模板.复合节点库.composite_空复合节点_示例_类格式 import 空复合节点_示例_类格式


GRAPH_VARIABLES: list[GraphVariableConfig] = []


class 模板示例_空复合节点_复合节点用法:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.空复合节点_示例_类格式 = 空复合节点_示例_类格式(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        self.空复合节点_示例_类格式.直接通过()
        打印字符串(self.game, 字符串="空复合节点：流程已通过")

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

