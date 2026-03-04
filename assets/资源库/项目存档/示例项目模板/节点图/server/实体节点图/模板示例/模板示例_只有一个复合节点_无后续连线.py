"""
graph_id: server_composite_lonely_example_01
graph_name: 模板示例_只有一个复合节点_无后续连线
graph_type: server
description: 示例节点图（仅一个复合节点）：在【实体创建时】调用一次复合节点但不连接其流程出口到任何后续节点，用于验证导出 .gia 时“未连线的复合节点/内部引脚”仍能被完整打包与对齐。
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

from 资源库.项目存档.示例项目模板.复合节点库.composite_多分支_示例_类格式 import 多分支_示例_类格式


GRAPH_VARIABLES: list[GraphVariableConfig] = []


class 模板示例_只有一个复合节点_无后续连线:
    """创建一个“孤立复合节点”场景：节点存在但流程出口不接任何后续逻辑。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.多分支_示例_类格式 = 多分支_示例_类格式(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 仅调用一次复合节点，不对流程出口做 match/连接
        self.多分支_示例_类格式.按整数多分支(分支值=0)

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

