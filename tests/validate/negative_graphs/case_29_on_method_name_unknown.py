"""
graph_id: neg_case_29_on_method_name_unknown
graph_name: 负例_29_on方法名未知事件
graph_type: server
description: 期望触发 CODE_ON_METHOD_NAME_UNKNOWN：任何 on_XXX 的 XXX 必须是内置事件名或已定义信号。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_29_on方法名未知事件:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_随便起名(self):
        pass


