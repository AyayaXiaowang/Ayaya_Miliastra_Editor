"""
graph_id: server_ts_suite_04_shared_composite_A
graph_name: TS_测试集_04_复用复合_A
graph_type: server
description: 回归测试：多图复用同一复合节点（A 图），用于验证 composite 定义/子图在 section10 的复用与去重。
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

from 资源库.项目存档.测试项目.复合节点库.composite_TS_合并引脚_扇出_v1 import TS_合并引脚_扇出_v1


GRAPH_VARIABLES: list[GraphVariableConfig] = []


class TS_测试集_04_复用复合_A:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.TS_合并引脚_扇出_v1 = TS_合并引脚_扇出_v1(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        self.TS_合并引脚_扇出_v1.扇出_双倍与平方(数值=3.0)

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

