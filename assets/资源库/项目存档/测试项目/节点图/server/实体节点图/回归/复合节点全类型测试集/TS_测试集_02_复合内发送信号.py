"""
graph_id: server_ts_suite_02_signal_inside_composite
graph_name: TS_测试集_02_复合内发送信号
graph_type: server
description: 回归测试：宿主图调用“复合内发送信号”复合节点，并监听同名信号事件（事件名=信号名），用于验证信号绑定与写回落盘。
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

from 资源库.项目存档.测试项目.复合节点库.composite_TS_复合内发送信号_v1 import TS_复合内发送信号_v1


TS_SIGNAL_NAME: str = "TS_Signal_AllTypes_001"


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="TS_信号_已收到",
        variable_type="布尔值",
        default_value=False,
        description="用于确认宿主图监听到来自复合节点的信号。",
        is_exposed=False,
    ),
]


class TS_测试集_02_复合内发送信号:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.TS_复合内发送信号_v1 = TS_复合内发送信号_v1(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        self.TS_复合内发送信号_v1.触发_全类型信号(
            数字A=42,
            数字B=1.25,
            文本="TS_信号_文本",
            是否启用=True,
            关联GUID=事件源GUID,
        )

    def on_TS_Signal_AllTypes_001(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        数字A: "整数",
        数字B: "浮点数",
        文本: "字符串",
        是否启用: "布尔值",
        关联GUID: "GUID",
    ):
        # 注意：这里的 handler 名不影响图结构；事件名由 register_event_handler 的第一个参数决定。
        设置节点图变量(
            self.game,
            变量名="TS_信号_已收到",
            变量值=True,
            是否触发事件=False,
        )

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )
        # 监听信号：事件名即信号名（发送信号节点在本地语义下会触发同名事件）
        self.game.register_event_handler(
            TS_SIGNAL_NAME,
            self.on_TS_Signal_AllTypes_001,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

