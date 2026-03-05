"""
graph_id: neg_case_02_if_condition_logic_not_call_in_if
graph_name: 负例_02_if条件_直接调用逻辑非运算
graph_type: server
description: 期望触发 if 条件规则：禁止在 if 条件中直接调用【逻辑非运算】。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_02_if条件_直接调用逻辑非运算:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        条件: "布尔值" = 是否相等(self.game, 输入1=1, 输入2=1)

        # 负例：if 条件中直接调用【逻辑非运算】
        if 逻辑非运算(self.game, 输入=条件):
            return


