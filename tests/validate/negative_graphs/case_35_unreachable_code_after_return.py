"""
graph_id: neg_case_35_unreachable_code_after_return
graph_name: 负例_35_return后不可达代码
graph_type: server
description: 期望触发 CODE_UNREACHABLE_AFTER_RETURN：return/raise 之后的语句不可达。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_35_return后不可达代码:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        return

        _不可达结果: "整数" = 加法运算(self.game, 左值=1, 右值=0)


