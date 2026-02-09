"""
graph_id: neg_case_20_lambda_forbidden
graph_name: 负例_20_lambda禁止
graph_type: server
description: 期望触发 CODE_NO_LAMBDA：禁止使用 lambda。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_20_lambda禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        _函数 = lambda x: x  # noqa: E731


