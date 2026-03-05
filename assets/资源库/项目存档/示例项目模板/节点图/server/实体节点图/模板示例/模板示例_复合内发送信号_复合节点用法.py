"""
graph_id: server_composite_signal_inside_example_01
graph_name: 模板示例_复合内发送信号_复合节点用法
graph_type: server
description: 示例节点图（复合节点内发送信号）：调用“复合内发送信号_示例_类格式”，用于验证导出 .gia 时递归收集复合节点子图内的 Send_Signal 并自包含打包信号 node_defs。
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

from 资源库.项目存档.示例项目模板.复合节点库.composite_复合内发送信号_示例_类格式 import 复合内发送信号_示例_类格式


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_复合内发送信号_已触发",
        variable_type="布尔值",
        default_value=False,
        description="用于确认宿主图已调用复合节点（复合节点内部会发送信号）。",
        is_exposed=False,
    ),
]


class 模板示例_复合内发送信号_复合节点用法:
    """宿主图调用“复合内发送信号”复合节点，验证导出 `.gia` 的信号自包含与复合子图递归。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        self.复合内发送信号_示例_类格式 = 复合内发送信号_示例_类格式(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        self.复合内发送信号_示例_类格式.广播踏板状态(是否激活=True)
        设置节点图变量(
            self.game,
            变量名="调试_复合内发送信号_已触发",
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

