"""
graph_id: server_template_loop_iterate_int_list
graph_name: 模板示例_循环遍历整数列表
graph_type: server
description: 示例节点图（for 遍历列表 + 累加）：在【实体创建时】构造整数列表并用 for 循环遍历一次，通过 `+=` 语法糖累加总和；把列表长度与总和写入节点图变量，便于在编辑器中观察循环与数据流。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir()))
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / 'assets'))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_列表长度",
        variable_type="整数",
        default_value=0,
        description="记录示例整数列表的长度，便于在编辑器中观察。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_元素总和",
        variable_type="整数",
        default_value=0,
        description="记录示例整数列表中所有元素求和的结果，便于在编辑器中观察。",
        is_exposed=False,
    ),
]

class 模板示例_循环遍历整数列表:
    """演示在节点图中结合 Python for 循环与节点函数遍历列表的最小用法。

    用法约定：
    - 本图挂载在任意 server 侧实体上，在【实体创建时】事件中运行一次；
    - 通过列表字面量 `[...]` 语法糖构造一个整数列表（会在校验/解析入口自动改写为【拼装列表】）；
    - 使用 for 循环逐个访问列表元素，在循环体内用 `+=` 语法糖累加总和（会自动改写为【加法运算】）；
    - 循环结束后，将“列表长度”和“元素总和”写入节点图变量，方便在编辑器中观察。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """实体创建完毕后，构造一个整数列表并用 for 循环遍历一次。"""
        整数列表示例值: "整数列表" = [1, 2, 3, 4, 5]

        当前循环次数: "整数" = len(整数列表示例值)
        当前总和: "整数" = 0

        for 当前元素 in 整数列表示例值:
            当前总和 += 当前元素

        设置节点图变量(
            self.game,
            变量名="调试_列表长度",
            变量值=当前循环次数,
            是否触发事件=False,
        )
        设置节点图变量(
            self.game,
            变量名="调试_元素总和",
            变量值=当前总和,
            是否触发事件=False,
        )

    # ---------------------------- 注册事件处理器 ----------------------------
    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )

if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))
