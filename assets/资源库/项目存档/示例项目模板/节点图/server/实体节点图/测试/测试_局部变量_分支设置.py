"""
graph_id: server_test_local_variable_branch_assign
graph_name: 测试_局部变量_分支设置
graph_type: server
description: 回归用例（if-else 分支合流写回）：分支前初始化局部变量，在 if/else 两侧分别写入不同结果，最后写入节点图变量便于观察；用于验证 IR 对【获取/设置局部变量】的建模正确性。
"""

from __future__ import annotations

import random
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

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_当前结果值",
        variable_type="整数",
        default_value=0,
        description="记录分支写回后的最终局部变量值（用于 UI 观察）。",
        is_exposed=False,
    ),
]


class 测试_局部变量_分支设置:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        当前结果值: "整数" = 0

        if random.randint(0, 1) == 0:
            当前结果值: "整数" = 10
        else:
            当前结果值: "整数" = 20

        设置节点图变量(
            self.game,
            变量名="调试_当前结果值",
            变量值=int(当前结果值),
            是否触发事件=False,
        )

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

