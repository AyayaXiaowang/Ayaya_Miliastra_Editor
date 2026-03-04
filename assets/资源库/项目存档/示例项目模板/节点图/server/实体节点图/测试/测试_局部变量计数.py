"""
graph_id: server_test_local_variable_counter
graph_name: 测试_局部变量计数
graph_type: server
description: 回归用例（循环体局部变量写回）：在 for 循环中重复更新局部变量并在 break 后使用，确保 IR 能建模为【获取/设置局部变量】写回，避免跨迭代更新丢失。
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
        name="调试_命中记录次数",
        variable_type="整数",
        default_value=0,
        description="记录本次回归用例中命中目标值的次数（用于 UI 观察）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_最近一次摇值",
        variable_type="整数",
        default_value=0,
        description="记录最终一次摇到的随机数结果（用于 UI 观察）。",
        is_exposed=False,
    ),
]


class 测试_局部变量计数:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        当前命中次数: "整数" = 0
        最近一次摇值: "整数" = 0

        for _轮次索引 in range(30):
            最近一次摇值: "整数" = random.randint(0, 2)
            if 最近一次摇值 == 1:
                当前命中次数 += 1
                if 当前命中次数 >= 3:
                    break

        设置节点图变量(
            self.game,
            变量名="调试_命中记录次数",
            变量值=int(当前命中次数),
            是否触发事件=False,
        )
        设置节点图变量(
            self.game,
            变量名="调试_最近一次摇值",
            变量值=int(最近一次摇值),
            是否触发事件=False,
        )

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

