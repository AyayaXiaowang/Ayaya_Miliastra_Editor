"""
graph_id: neg_case_14_list_literal_for_iter_forbidden
graph_name: 负例_14_for迭代器位置_列表字面量禁止
graph_type: server
description: 期望触发 CODE_LIST_LITERAL_FOR_ITER_FORBIDDEN：for 的迭代器位置禁止直接使用列表字面量。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_14_for迭代器位置_列表字面量禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        for _元素 in [1, 2, 3]:
            pass


