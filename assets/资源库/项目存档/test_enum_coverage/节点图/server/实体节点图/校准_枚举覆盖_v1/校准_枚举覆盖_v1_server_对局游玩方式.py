"""
graph_id: server_enum_coverage_match_mode_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_server_对局游玩方式
graph_type: server
description: 枚举覆盖图（拆分版）：查询节点【查询对局游玩方式及人数】的游玩方式输出枚举候选项覆盖；每个事件 ≤ 20 节点。
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


class 校准_枚举覆盖_v1_server_对局游玩方式:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        __handle, __value = 获取局部变量(self.game, 初始值=False)
        设置局部变量(self.game, 局部变量=__handle, 值=__value)

        __游玩人数, __游玩方式 = 查询对局游玩方式及人数(self.game)
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=__游玩方式, 枚举2="试玩"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=__游玩方式, 枚举2="房间游玩"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=__游玩方式, 枚举2="匹配游玩"))

        return

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))


