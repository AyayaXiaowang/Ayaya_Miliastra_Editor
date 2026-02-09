"""
graph_id: neg_case_13_list_literal_starred_forbidden
graph_name: 负例_13_列表字面量星号解包禁止
graph_type: server
description: 期望触发 CODE_LIST_LITERAL_STARRED_NOT_SUPPORTED：列表字面量不支持 * 解包语法（例如 [*xs]）。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_13_列表字面量星号解包禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        基础列表: "整数列表" = [1, 2, 3]
        _解包列表: "整数列表" = [*基础列表]


