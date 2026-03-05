"""
graph_id: neg_case_23_local_var_initial_required
graph_name: 负例_23_获取局部变量_缺少初始值
graph_type: server
description: 期望触发 CODE_LOCAL_VAR_INITIAL_REQUIRED：获取局部变量(...) 必须提供 初始值。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_23_获取局部变量_缺少初始值:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 负例：未提供初始值（用下标选择避免叠加“必须二元解包”的报错）
        _当前值: "整数" = 获取局部变量(self.game)[1]


