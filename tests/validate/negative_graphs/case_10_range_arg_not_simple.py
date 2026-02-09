"""
graph_id: neg_case_10_range_arg_not_simple
graph_name: 负例_10_range_参数内联算术表达式禁止
graph_type: server
description: 期望触发 CODE_RANGE_ARG_NOT_SIMPLE：range(...) 参数禁止内联算术/调用/下标等复杂表达式。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_10_range_参数内联算术表达式禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        for _序号 in range(1 + 2):
            pass


