"""
graph_id: neg_case_08_range_keywords_forbidden
graph_name: 负例_08_range_关键字参数禁止
graph_type: server
description: 期望触发 CODE_RANGE_CALL_KEYWORDS_FORBIDDEN：range(...) 禁止使用关键字参数。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_08_range_关键字参数禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        for _序号 in range(start=0, stop=3):
            pass


