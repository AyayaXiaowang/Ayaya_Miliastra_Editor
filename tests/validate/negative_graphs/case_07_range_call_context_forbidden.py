"""
graph_id: neg_case_07_range_call_context_forbidden
graph_name: 负例_07_range_非for迭代器位置调用
graph_type: server
description: 期望触发 CODE_RANGE_CALL_CONTEXT_FORBIDDEN：range(...) 仅允许出现在 for 的迭代器位置。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_07_range_非for迭代器位置调用:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 负例：range 不能出现在普通赋值/表达式中
        _序号范围 = range(3)


