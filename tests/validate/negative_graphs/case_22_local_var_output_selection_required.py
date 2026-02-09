"""
graph_id: neg_case_22_local_var_output_selection_required
graph_name: 负例_22_获取局部变量_必须选择输出
graph_type: server
description: 期望触发 CODE_LOCAL_VAR_OUTPUT_SELECTION_REQUIRED：获取局部变量(...) 有 2 个输出，必须二元解包或下标取值。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_22_获取局部变量_必须选择输出:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 负例：把“二元输出”当作单值使用
        _错误用法: "整数" = 获取局部变量(self.game, 初始值=0)


