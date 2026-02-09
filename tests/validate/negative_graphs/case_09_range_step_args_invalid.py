"""
graph_id: neg_case_09_range_step_args_invalid
graph_name: 负例_09_range_不支持step参数
graph_type: server
description: 期望触发 CODE_RANGE_CALL_ARGS_COUNT_INVALID：range(...) 仅支持 1 或 2 个位置参数（禁止 step）。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_09_range_不支持step参数:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        for _序号 in range(0, 10, 2):
            pass


