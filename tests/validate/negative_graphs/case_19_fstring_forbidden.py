"""
graph_id: neg_case_19_fstring_forbidden
graph_name: 负例_19_fstring禁止
graph_type: server
description: 期望触发 CODE_NO_FSTRING：禁止使用 f-string。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_19_fstring禁止:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数值: "整数" = 加法运算(self.game, 左值=1, 右值=0)
        _文本: "字符串" = f"值={整数值}"


