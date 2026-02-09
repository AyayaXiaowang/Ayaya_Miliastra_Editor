"""
graph_id: neg_case_30_event_handler_signature_invalid
graph_name: 负例_30_内置事件回调签名不匹配
graph_type: server
description: 期望触发 CODE_EVENT_HANDLER_SIGNATURE_MISMATCH：内置事件回调 on_<事件名> 的参数必须与事件节点输出端口一致。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_30_内置事件回调签名不匹配:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    # 负例：内置事件“实体创建时”通常至少包含 (事件源实体, 事件源GUID)；这里故意缺少参数
    def on_实体创建时(self, 事件源实体):
        return

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


