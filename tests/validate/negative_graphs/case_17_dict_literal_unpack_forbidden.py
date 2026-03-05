"""
graph_id: neg_case_17_dict_literal_unpack_forbidden
graph_name: 负例_17_字典解包语法禁止
graph_type: server
description: 期望触发 CODE_DICT_LITERAL_UNPACK_NOT_SUPPORTED：禁止 {**d} 这类字典解包语法。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_17_字典解包语法禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        基础字典: "字符串-整数字典" = {"a": 1}
        _解包字典: "字符串-整数字典" = {**基础字典}


