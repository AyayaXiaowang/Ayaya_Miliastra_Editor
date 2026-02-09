"""
graph_id: neg_case_21_match_case_pattern_not_literal
graph_name: 负例_21_match_case模式必须字面量
graph_type: server
description: 期望触发 CODE_MATCH_CASE_PATTERN_NOT_LITERAL：case pattern 禁止使用变量/属性/表达式。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_21_match_case模式必须字面量:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        待匹配值: "整数" = 加法运算(self.game, 左值=2, 右值=0)
        非字面量模式: "整数" = 加法运算(self.game, 左值=1, 右值=0)

        match 待匹配值:
            # 注意：capture pattern 若不在最后一个 case，会被 Python 判定为“吞掉后续分支”，从而直接触发语法错误。
            # 本负例只保留单个 case：确保文件语法可编译，同时用于触发校验器的“pattern 非字面量”规则。
            case 非字面量模式:
                return


