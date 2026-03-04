"""
graph_id: neg_case_28_const_alias_assignment_forbidden
graph_name: 负例_28_命名常量禁止别名复制
graph_type: server
description: 期望触发 CODE_NO_CONST_ALIAS_ASSIGNMENT：命名常量在别名前被运行期赋值覆盖后，不允许再做常量别名复制。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_28_命名常量禁止别名复制:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 该写法属于允许的“命名常量”声明（AnnAssign + 中文类型注解 + 字面量）
        常量配置: "配置ID" = "1077936129"

        # 运行期覆盖：别名点之前，源变量已不再是“稳定常量”
        常量配置 = 加法运算(self.game, 左值=常量配置, 右值=1)

        # 负例：禁止通过赋值把命名常量复制到别名变量
        _别名配置 = 常量配置


