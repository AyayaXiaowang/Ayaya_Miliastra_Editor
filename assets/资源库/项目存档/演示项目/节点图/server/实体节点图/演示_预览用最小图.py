"""
graph_id: server_demo_package_preview_graph
graph_name: 演示_预览用最小图
graph_type: server
description: 回归夹具：用于 Packages 页在“当前作用域不等于预览目标存档”时，仍可扫描并展示至少 1 张节点图（不依赖 ResourceManager 当前 active_package_id）。
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


GRAPH_VARIABLES: list[GraphVariableConfig] = []


class 演示_预览用最小图:
    """最小可校验节点图：实体创建时写入一个自定义变量。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        设置自定义变量(
            self.game,
            目标实体=self.owner_entity,
            变量名="演示_预览用最小图_已触发",
            变量值=True,
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

