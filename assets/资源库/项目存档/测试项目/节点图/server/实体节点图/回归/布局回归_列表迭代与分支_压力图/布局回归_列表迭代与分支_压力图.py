"""
graph_id: ts_layout_regression_list_iter_branches_stress_01
graph_name: 布局回归_列表迭代与分支_压力图
graph_type: server
description: |
  压力回归节点图（布局/分块/端口顺序）：
  - 密集包含多个列表迭代循环（for x in 列表）；
  - 循环体内混合双分支（if/else）与多分支（match-case）；
  - 每个循环都保证“循环完成”后仍有后续流程，从而同时存在 `循环体/循环完成` 两出口链路，
    便于复现与验证块编号不变量（循环体子块必须早于循环完成子块）。
folder_path: 测试项目/节点图/server/实体节点图/回归/布局回归_列表迭代与分支_压力图
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = next(
    p
    for p in Path(__file__).resolve().parents
    if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir())
)
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / "assets"))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403

# ------------------------------ 常量（避免魔法数字） ------------------------------
INT_0: int = 0
INT_1: int = 1
INT_2: int = 2
INT_3: int = 3
INT_4: int = 4
INT_5: int = 5
INT_6: int = 6
INT_7: int = 7
INT_8: int = 8
INT_9: int = 9

TEXT_A: str = "A"
TEXT_B: str = "B"
TEXT_C: str = "C"
TEXT_D: str = "D"
TEXT_E: str = "E"

TAG_LOOP_1: str = "loop_1"
TAG_LOOP_2: str = "loop_2"
TAG_LOOP_3: str = "loop_3"
TAG_LOOP_4: str = "loop_4"

RANDOM_LO: int = INT_0
RANDOM_HI: int = INT_4
BREAK_ON_SUM: int = INT_9


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_路径",
        variable_type="字符串",
        default_value="init",
        description="记录当前走到的分支路径标记（用于可视化观察多分支/双分支/循环完成链路）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_总和",
        variable_type="整数",
        default_value=0,
        description="多个循环累加的总和（用于让循环体内数据流更复杂）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_日志",
        variable_type="字符串列表",
        default_value=[],
        description="记录关键步骤（循环体/循环完成/分支路径）以便观察执行顺序。",
        is_exposed=False,
    ),
]


class 布局回归_列表迭代与分支_压力图:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 初始化
        设置节点图变量(self.game, 变量名="调试_路径", 变量值="start", 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_总和", 变量值=INT_0, 是否触发事件=False)

        # ------------------------------ 循环1：整数列表 + 双分支 + 多分支 ------------------------------
        列表1: "整数列表" = [INT_1, INT_2, INT_3, INT_4, INT_5]
        for 元素1 in 列表1:
            # 双分支：偶数/奇数
            是否偶数 = (元素1 % INT_2) == INT_0
            if 是否偶数:
                设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_1:even", 是否触发事件=False)
            else:
                设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_1:odd", 是否触发事件=False)

            # 多分支：根据随机值走不同路径（match 会生成 多分支）
            随机值1 = 获取随机整数(self.game, 下限=RANDOM_LO, 上限=RANDOM_HI)
            match 随机值1:
                case 0:
                    设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_1:case0", 是否触发事件=False)
                case 1:
                    设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_1:case1", 是否触发事件=False)
                case 2:
                    设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_1:case2", 是否触发事件=False)
                case _:
                    设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_1:case_other", 是否触发事件=False)

            # 累加总和：让数据线跨越多个流程节点
            当前总和1: "整数" = 获取节点图变量(self.game, 变量名="调试_总和")
            新总和1: "整数" = 当前总和1 + 元素1
            设置节点图变量(self.game, 变量名="调试_总和", 变量值=新总和1, 是否触发事件=False)

            # 循环体内的 break（增加控制流复杂度）
            if 新总和1 >= BREAK_ON_SUM:
                设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_1:break", 是否触发事件=False)
                break

            # 记录日志：字符串列表（会触发列表拼装/类型转换链路）
            文本1: "字符串" = str(新总和1)
            随机值1_文本: "字符串" = str(随机值1)
            日志条目1: "字符串列表" = [TAG_LOOP_1, 随机值1_文本, 文本1]
            设置节点图变量(self.game, 变量名="调试_日志", 变量值=日志条目1, 是否触发事件=False)

        # 循环1完成后的后续流程（确保存在“循环完成”出口链路）
        设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_1:done", 是否触发事件=False)

        # ------------------------------ 循环2：字符串列表 + 双分支嵌套 ------------------------------
        列表2: "字符串列表" = [TEXT_A, TEXT_B, TEXT_C, TEXT_D, TEXT_E]
        for 元素2 in 列表2:
            是否C = 元素2 == TEXT_C
            if 是否C:
                设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_2:hitC", 是否触发事件=False)
                break
            else:
                # 内层双分支：A/B 走不同标记
                是否A = 元素2 == TEXT_A
                if 是否A:
                    设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_2:isA", 是否触发事件=False)
                else:
                    设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_2:notA", 是否触发事件=False)

        设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_2:done", 是否触发事件=False)

        # ------------------------------ 循环3：多列表交织（循环体内再做 match） ------------------------------
        列表3: "整数列表" = [INT_6, INT_7, INT_8, INT_9]
        for 元素3 in 列表3:
            当前总和3: "整数" = 获取节点图变量(self.game, 变量名="调试_总和")
            新总和3: "整数" = 当前总和3 + 元素3
            设置节点图变量(self.game, 变量名="调试_总和", 变量值=新总和3, 是否触发事件=False)

            # 多分支：基于元素值分桶
            match 元素3:
                case 6:
                    设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_3:k6", 是否触发事件=False)
                case 7:
                    设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_3:k7", 是否触发事件=False)
                case 8:
                    设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_3:k8", 是否触发事件=False)
                case _:
                    设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_3:k_other", 是否触发事件=False)

        设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_3:done", 是否触发事件=False)

        # ------------------------------ 循环4：列表迭代 + 循环完成后再分支 ------------------------------
        列表4: "整数列表" = [INT_2, INT_4, INT_6, INT_8]
        for 元素4 in 列表4:
            当前总和4: "整数" = 获取节点图变量(self.game, 变量名="调试_总和")
            新总和4: "整数" = 当前总和4 + 元素4
            设置节点图变量(self.game, 变量名="调试_总和", 变量值=新总和4, 是否触发事件=False)
            if 新总和4 > (INT_8 + INT_1):
                设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_4:gt9", 是否触发事件=False)
            else:
                设置节点图变量(self.game, 变量名="调试_路径", 变量值="loop_4:le9", 是否触发事件=False)

        # 循环4完成后：再来一个多分支，确保循环完成出口下方也有分块
        最终值: "整数" = 获取节点图变量(self.game, 变量名="调试_总和")
        match 最终值:
            case 0:
                设置节点图变量(self.game, 变量名="调试_路径", 变量值="final:sum0", 是否触发事件=True)
            case 1:
                设置节点图变量(self.game, 变量名="调试_路径", 变量值="final:sum1", 是否触发事件=True)
            case 2:
                设置节点图变量(self.game, 变量名="调试_路径", 变量值="final:sum2", 是否触发事件=True)
            case _:
                设置节点图变量(self.game, 变量名="调试_路径", 变量值="final:sum_other", 是否触发事件=True)

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

