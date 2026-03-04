"""
graph_id: server_test_composite_inner_signal_01
graph_name: 测试_复合节点_复合内发送信号
graph_type: server
description: 回归用例：宿主图调用“复合内发送信号_示例_类格式”，信号在复合节点子图内部发送；用于验证导出 .gia 时递归收集复合节点内部使用到的信号定义并打包。
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
        name="调试_是否激活",
        variable_type="布尔值",
        default_value=False,
        description="用于记录本次调用传入的是否激活参数（便于观察）。",
        is_exposed=False,
    ),
]


class 测试_复合节点_复合内发送信号:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        self.复合内发送信号_示例_类格式 = 复合内发送信号_示例_类格式(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        设置节点图变量(self.game, 变量名="调试_是否激活", 变量值=True, 是否触发事件=False)
        self.复合内发送信号_示例_类格式.广播踏板状态(是否激活=True)

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

