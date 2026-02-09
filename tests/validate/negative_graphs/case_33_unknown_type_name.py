"""
graph_id: neg_case_33_unknown_type_name
graph_name: 负例_33_未知类型名
graph_type: server
description: 期望触发 CODE_UNKNOWN_TYPE_NAME：中文类型注解必须使用引擎支持的数据类型名称。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_33_未知类型名:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 负例：不存在的类型名
        _奇怪变量: "火箭科学" = 加法运算(self.game, 左值=1, 右值=0)


