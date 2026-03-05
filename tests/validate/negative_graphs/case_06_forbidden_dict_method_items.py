"""
graph_id: neg_case_06_forbidden_dict_method_items
graph_name: 负例_06_禁止_dict_items方法调用
graph_type: server
description: 期望触发 CODE_NO_METHOD_CALL：禁止调用 dict.items() 等未被语法糖改写支持的方法。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_06_禁止_dict_items方法调用:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        示例字典: "字符串-整数字典" = {"a": 1, "b": 2}

        # 负例：items() 不在允许的语法糖范围内，会被“方法调用禁用”规则拦截
        _条目列表: "泛型列表" = 示例字典.items()


