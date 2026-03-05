"""
graph_id: neg_case_01_if_condition_python_expr
graph_name: 负例_01_if条件_直接写Python比较表达式
graph_type: server
description: 期望触发 Compare 相关语法糖禁用：链式比较在 Graph Code 中不支持（应拆成多个布尔变量并用逻辑节点组合）。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_01_if条件_直接写Python比较表达式:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        整数A: "整数" = 加法运算(self.game, 左值=1, 右值=0)
        整数B: "整数" = 加法运算(self.game, 左值=2, 右值=0)

        # 负例：链式比较不支持（a < b < c）
        if 整数A < 整数B < 3:
            return
        # 负例：另一种常见链式写法（in 连续出现）
        if 整数A in 整数B in [1, 2, 3]:
            return


