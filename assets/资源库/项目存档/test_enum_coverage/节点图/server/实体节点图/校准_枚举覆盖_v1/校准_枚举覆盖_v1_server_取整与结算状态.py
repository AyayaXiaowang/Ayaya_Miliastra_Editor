"""
graph_id: server_enum_coverage_rounding_and_settlement_state_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_server_取整与结算状态
graph_type: server
description: 枚举覆盖图（拆分版）：覆盖取整方式(4)与结算状态(未定/胜利/失败)；每个事件 ≤ 20 节点。
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


class 校准_枚举覆盖_v1_server_取整与结算状态:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        __取整_向上 = 取整数运算(self.game, 输入=1.25, 取整方式="取整逻辑_向上取整")
        __取整_向下 = 取整数运算(self.game, 输入=1.25, 取整方式="取整逻辑_向下取整")
        __取整_四舍五入 = 取整数运算(self.game, 输入=1.25, 取整方式="取整逻辑_四舍五入")
        __取整_截尾 = 取整数运算(self.game, 输入=1.25, 取整方式="取整逻辑_截尾取整")

        设置玩家段位变化分数(self.game, 玩家实体=事件源实体, 结算状态="未定", 变化分数=__取整_向上)
        设置玩家段位变化分数(self.game, 玩家实体=事件源实体, 结算状态="胜利", 变化分数=__取整_向下)
        设置玩家段位变化分数(self.game, 玩家实体=事件源实体, 结算状态="失败", 变化分数=__取整_四舍五入)

        __int_handle, __int_value = 获取局部变量(self.game, 初始值=0)
        设置局部变量(self.game, 局部变量=__int_handle, 值=__int_value)
        设置局部变量(self.game, 局部变量=__int_handle, 值=__取整_截尾)

        return

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))


