"""
graph_id: neg_case_34_port_same_type_required
graph_name: 负例_34_端口同型输入要求
graph_type: server
description: 期望触发 PORT_SAME_TYPE_REQUIRED：部分节点（如 是否相等）输入端口必须同型（整数≠浮点数）。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_34_端口同型输入要求:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数值: "整数" = 加法运算(self.game, 左值=1, 右值=0)
        浮点值: "浮点数" = 加法运算(self.game, 左值=1.0, 右值=0.0)

        _比较结果: "布尔值" = 是否相等(self.game, 输入1=整数值, 输入2=浮点值)


