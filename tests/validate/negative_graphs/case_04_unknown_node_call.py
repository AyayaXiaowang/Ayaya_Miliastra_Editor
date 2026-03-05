"""
graph_id: neg_case_04_unknown_node_call
graph_name: 负例_04_未知节点调用
graph_type: server
description: 期望触发 UnknownNodeCallRule：疑似节点调用但节点库中不存在（拼写错误/未登记）。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_04_未知节点调用:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 负例：节点库中不存在该节点
        _结果: "整数" = 不存在的节点(self.game, 输入1=1, 输入2=2)


