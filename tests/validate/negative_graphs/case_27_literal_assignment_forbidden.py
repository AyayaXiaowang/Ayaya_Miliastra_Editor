"""
graph_id: neg_case_27_literal_assignment_forbidden
graph_name: 负例_27_禁止直接常量赋值
graph_type: server
description: 期望触发 CODE_NO_LITERAL_ASSIGNMENT：禁止在节点图方法体中直接将常量赋值给变量。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_27_禁止直接常量赋值:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 负例：直接常量赋值（不带“命名常量”注解形式）
        _整数值 = 1


