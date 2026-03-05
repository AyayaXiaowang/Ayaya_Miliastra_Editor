"""
graph_id: server_template_syntax_sugar_auto_shared_composites__测试基础内容
graph_name: 模板示例_语法糖_自动共享复合节点
graph_type: server
description: 示例节点图：演示 Graph Code 的语法糖改写如何自动转为“共享复合节点”调用（any/all/sum、整数列表切片、整数/浮点数三元表达式）。
"""

from __future__ import annotations

import sys
import random
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir()))
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / 'assets'))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_三元_整数结果",
        variable_type="整数",
        default_value=0,
        description="三元表达式（整数）改写后的结果。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_三元_浮点数结果",
        variable_type="浮点数",
        default_value=0.0,
        description="三元表达式（浮点数）改写后的结果。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_切片长度",
        variable_type="整数",
        default_value=0,
        description="整数列表切片后的长度。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_any结果",
        variable_type="布尔值",
        default_value=False,
        description="any(布尔值列表) 的结果。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_all结果",
        variable_type="布尔值",
        default_value=False,
        description="all(布尔值列表) 的结果。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_sum结果",
        variable_type="整数",
        default_value=0,
        description="sum(整数列表) 的结果。",
        is_exposed=False,
    ),
]

class 模板示例_语法糖_自动共享复合节点:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # ===== 1) 三元表达式：整数 =====
        随机整数: "整数" = random.randint(0, 10)
        是否大于五: "布尔值" = 随机整数 > 5
        三元_整数结果: "整数" = 111 if 是否大于五 else 222

        # ===== 2) 三元表达式：浮点数 =====
        随机浮点数: "浮点数" = random.uniform(0.0, 1.0)
        是否大于零点五: "布尔值" = 随机浮点数 > 0.5
        三元_浮点数结果: "浮点数" = 1.25 if 是否大于零点五 else 9.75

        # ===== 3) 整数列表切片 =====
        整数列表: "整数列表" = [1, 2, 3, 4, 5, 6]
        子列表: "整数列表" = 整数列表[2:5]
        子列表长度: "整数" = len(子列表)

        # ===== 4) any / all =====
        布尔值列表: "布尔值列表" = [False, True, False]
        any结果: "布尔值" = any(布尔值列表)
        all结果: "布尔值" = all(布尔值列表)

        # ===== 5) sum =====
        sum结果: "整数" = sum(整数列表)

        设置节点图变量(self.game, 变量名="调试_三元_整数结果", 变量值=三元_整数结果, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_三元_浮点数结果", 变量值=三元_浮点数结果, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_切片长度", 变量值=子列表长度, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_any结果", 变量值=any结果, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_all结果", 变量值=all结果, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_sum结果", 变量值=sum结果, 是否触发事件=False)

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )

if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))
