"""
graph_id: server_ts_suite_03_nested_composite
graph_name: TS_测试集_03_嵌套复合
graph_type: server
description: 回归测试：宿主图调用“嵌套复合_组合_v1”（复合内调用复合 + 复合内发送信号），用于验证递归收集与写回落盘。
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

from 资源库.项目存档.测试项目.复合节点库.composite_TS_嵌套复合_组合_v1 import TS_嵌套复合_组合_v1


GRAPH_VARIABLES: list[GraphVariableConfig] = []


class TS_测试集_03_嵌套复合:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.TS_嵌套复合_组合_v1 = TS_嵌套复合_组合_v1(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        self.TS_嵌套复合_组合_v1.组合流程(
            数值=2.0,
            文本="TS_nested",
            事件GUID=事件源GUID,
            事件实体=事件源实体,
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

