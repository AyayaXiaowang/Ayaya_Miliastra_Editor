"""
graph_id: neg_case_32_graph_var_declaration_missing
graph_name: 负例_32_节点图变量未声明
graph_type: server
description: 期望触发 CODE_GRAPH_VAR_DECLARATION：设置/获取节点图变量的变量名必须在 GRAPH_VARIABLES 中声明。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_32_节点图变量未声明:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 负例：文件顶部没有 GRAPH_VARIABLES 声明，却读写了图变量
        设置节点图变量(self.game, 变量名="未声明的图变量", 变量值=0, 是否触发事件=False)
        _值: "整数" = 获取节点图变量(self.game, 变量名="未声明的图变量")


