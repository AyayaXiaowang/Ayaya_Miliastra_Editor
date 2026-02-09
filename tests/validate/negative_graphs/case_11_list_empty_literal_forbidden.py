"""
graph_id: neg_case_11_list_empty_literal_forbidden
graph_name: 负例_11_空列表字面量禁止
graph_type: server
description: 期望触发 CODE_EMPTY_LIST_LITERAL_FORBIDDEN：禁止定义空列表字面量 []。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_11_空列表字面量禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        _空列表: "整数列表" = []


