"""
graph_id: neg_case_26_variadic_min_args_forbidden
graph_name: 负例_26_可变参数节点不允许空参数
graph_type: server
description: 期望触发 CODE_VARIADIC_MIN_ARGS：可变参数节点至少提供指定数量的数据入参（例如【拼装列表】至少 1 个）。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_26_可变参数节点不允许空参数:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 负例：仅传 self.game，没有任何数据入参
        _列表: "整数列表" = 拼装列表(self.game)


