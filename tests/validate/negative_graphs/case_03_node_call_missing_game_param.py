"""
graph_id: neg_case_03_node_call_missing_game_param
graph_name: 负例_03_节点调用_缺少game参数
graph_type: server
description: 期望触发 NodeCallGameRequiredRule：节点函数调用必须显式传入 game（通常为 self.game）。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_03_节点调用_缺少game参数:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 负例：缺少 self.game
        结果: "整数" = 加法运算(左值=1, 右值=2)

        if 是否相等(self.game, 输入1=结果, 输入2=3):
            return


