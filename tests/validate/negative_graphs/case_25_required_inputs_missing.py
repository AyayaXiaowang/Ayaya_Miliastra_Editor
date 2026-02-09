"""
graph_id: neg_case_25_required_inputs_missing
graph_name: 负例_25_节点调用缺少必填入参
graph_type: server
description: 期望触发 CODE_NODE_MISSING_REQUIRED_INPUTS：节点调用必须提供所有必填输入端口。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_25_节点调用缺少必填入参:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 负例：加法运算缺少必填端口『右值』
        _结果: "整数" = 加法运算(self.game, 左值=1)


