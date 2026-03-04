"""
graph_id: server_ts_min_bool_01
graph_name: TS_最小复现_布尔复合调用
graph_type: server
description: 最小复现：宿主图只包含一个复合节点实例（TS_最小布尔复合_v1），且只用一个布尔虚拟引脚。
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
from 资源库.项目存档.测试项目.复合节点库.composite_TS_最小布尔复合_v1 import TS_最小布尔复合_v1


class TS_最小复现_布尔复合调用:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.TS_最小布尔复合_v1 = TS_最小布尔复合_v1(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 关键：写死一个布尔常量，避免任何“从边推断类型”的分支干扰。
        self.TS_最小布尔复合_v1.触发布尔链路(布尔值=True)

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

