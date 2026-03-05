"""
graph_id: neg_case_05_forbidden_python_builtin_sorted
graph_name: 负例_05_禁止_python内置sorted调用
graph_type: server
description: 期望触发“非节点函数调用禁用”规则：sorted(...) 属于 Python 函数调用，无法被 IR 建模。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_05_禁止_python内置sorted调用:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        目标列表: "整数列表" = [3, 1, 2]

        # 负例：Python 内置 sorted 调用
        _排序后列表: "整数列表" = sorted(目标列表)


