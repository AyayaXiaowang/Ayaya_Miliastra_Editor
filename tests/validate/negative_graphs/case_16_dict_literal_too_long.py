"""
graph_id: neg_case_16_dict_literal_too_long
graph_name: 负例_16_字典字面量超过上限
graph_type: server
description: 期望触发 CODE_DICT_LITERAL_TOO_LONG：字典字面量键值对数量超过上限（默认 50）。
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 负例_16_字典字面量超过上限:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        _超长字典: "字符串-整数字典" = {
            "k01": 1, "k02": 2, "k03": 3, "k04": 4, "k05": 5,
            "k06": 6, "k07": 7, "k08": 8, "k09": 9, "k10": 10,
            "k11": 11, "k12": 12, "k13": 13, "k14": 14, "k15": 15,
            "k16": 16, "k17": 17, "k18": 18, "k19": 19, "k20": 20,
            "k21": 21, "k22": 22, "k23": 23, "k24": 24, "k25": 25,
            "k26": 26, "k27": 27, "k28": 28, "k29": 29, "k30": 30,
            "k31": 31, "k32": 32, "k33": 33, "k34": 34, "k35": 35,
            "k36": 36, "k37": 37, "k38": 38, "k39": 39, "k40": 40,
            "k41": 41, "k42": 42, "k43": 43, "k44": 44, "k45": 45,
            "k46": 46, "k47": 47, "k48": 48, "k49": 49, "k50": 50,
            "k51": 51,
        }


