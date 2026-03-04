"""
graph_id: server_template_local_variable_counter
graph_name: 模板示例_局部变量计数
graph_type: server
description: 示例节点图（局部变量计数 + break）：在【实体创建时】循环摇随机数，命中 1 达到 3 次后 break 退出；通过变量赋值与 `+=` 语法糖表达计数逻辑（IR 会自动建模局部变量节点），并把结果写入节点图变量便于观察。
"""

import sys
import random
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir()))
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / 'assets'))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="命中记录次数",
        variable_type="整数",
        default_value=0,
        description="记录本次示例中命中目标值的次数，便于在编辑器中观察",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="最近一次摇值",
        variable_type="整数",
        default_value=0,
        description="记录最终一次摇到的随机数结果，便于在编辑器中观察",
        is_exposed=False,
    ),
]

class 模板示例_局部变量计数:
    """演示局部变量（由 IR 自动建模）的最小流程：

    1. 用节点输出初始化计数与记录值（避免直接字面量赋值）；
    2. 在循环内当检测到随机数为 1 时累加（多次赋值会在 IR 中自动建模为局部变量更新）；
    3. 当命中次数达到 3 次后立即退出循环，并把结果写入节点图变量，方便 UI 观察。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        当前命中次数: "整数" = 0
        最近一次摇值: "整数" = 0
        for 轮次索引 in range(30):
            最近一次摇值: "整数" = random.randint(0, 2)

            if 最近一次摇值 == 1:
                当前命中次数 += 1
                if 当前命中次数 >= 3:
                    break

        设置节点图变量(self.game, 变量名="命中记录次数", 变量值=int(当前命中次数), 是否触发事件=False)
        设置节点图变量(self.game, 变量名="最近一次摇值", 变量值=int(最近一次摇值), 是否触发事件=False)

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)

if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))
