"""
graph_id: neg_case_31_event_name_unknown
graph_name: 负例_31_未知事件名
graph_type: server
description: 期望触发 CODE_UNKNOWN_EVENT_NAME：register_event_handler 注册的事件名必须是内置事件或信号。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_31_未知事件名:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        return

    def register_handlers(self):
        # 负例：不存在的事件名
        self.game.register_event_handler("不存在事件", self.on_实体创建时, owner=self.owner_entity)


