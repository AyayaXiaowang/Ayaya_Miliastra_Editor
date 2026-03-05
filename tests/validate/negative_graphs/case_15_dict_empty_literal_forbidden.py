"""
graph_id: neg_case_15_dict_empty_literal_forbidden
graph_name: 负例_15_空字典字面量禁止
graph_type: server
description: 期望触发 CODE_EMPTY_DICT_LITERAL_FORBIDDEN：禁止定义空字典字面量 {}。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_15_空字典字面量禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        _空字典: "字符串-整数字典" = {}


