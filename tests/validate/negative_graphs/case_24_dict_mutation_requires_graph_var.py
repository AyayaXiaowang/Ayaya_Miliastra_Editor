"""
graph_id: neg_case_24_dict_mutation_requires_graph_var
graph_name: 负例_24_字典原地修改后继续使用_必须落图变量
graph_type: server
description: |
  期望触发 CODE_DICT_MUTATION_REQUIRES_GRAPH_VAR：
  当字典来源于【拼装字典/建立字典】等计算节点的输出时，若“原地修改后仍在后续流程中继续使用”，
  由于可能重复求值导致写回语义不可靠，必须改为【节点图变量】承载。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_24_字典原地修改后继续使用_必须落图变量:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        目标实体: "实体" = 事件源实体
        _事件源GUID: "GUID" = 事件源GUID

        # 字典来源：字典字面量会改写为【拼装字典】运算节点（计算结果 dict）
        临时字典: "字符串-整数字典" = {"a": 1, "b": 2}

        # 原地修改（会改写为【对字典设置或新增键值对】执行节点）
        临时字典["a"] = 999

        # 修改后继续使用：构造一个后续“流程节点”并依赖该字典（用于触发“写回语义必须落图变量”的静态分析）
        修改后长度: "整数" = len(临时字典)
        设置自定义变量(
            self.game,
            目标实体=目标实体,
            变量名="负例_字典修改后长度",
            变量值=修改后长度,
            是否触发事件=False,
        )


