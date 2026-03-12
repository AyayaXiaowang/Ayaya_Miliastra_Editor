"""
graph_id: server_template_local_variable_branch_assign
graph_name: 模板示例_局部变量_分支设置
graph_type: server
description: 示例节点图（if-else 分支写入结果）：在【实体创建时】用随机分支索引驱动 if-else，并在不同分支中写入不同的最终结果到节点图变量；同时写入分支索引，便于在编辑器中观察分支与数据流。
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
        name="调试_分支索引",
        variable_type="整数",
        default_value=0,
        description="记录本次随机选择的分支索引，便于在编辑器中观察。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_最终结果",
        variable_type="整数",
        default_value=0,
        description="记录根据分支写入的最终局部变量值，便于在编辑器中观察。",
        is_exposed=False,
    ),
]

class 模板示例_局部变量_分支设置:
    """演示在 if-else 分支中计算不同结果并写入节点图变量的最小用法。

    用法约定：
    - 本图挂载在任意 server 侧实体上，在【实体创建时】事件中运行一次；
    - 首先使用【获取随机整数】随机生成一个分支索引，写入节点图变量；
    - 在 if-else 分支中分别计算结果，并写入节点图变量，方便在编辑器中观察。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """实体创建完毕后，随机选择一个分支，并在分支中写入不同的结果值。"""
        分支索引: "整数" = random.randint(0, 1)
        当前结果值: "整数" = 0
        设置节点图变量(
            self.game,
            变量名="调试_分支索引",
            变量值=分支索引,
            是否触发事件=False,
        )

        if 分支索引 == 0:
            当前结果值: "整数" = 10
        else:
            当前结果值: "整数" = 20

        设置节点图变量(
            self.game,
            变量名="调试_最终结果",
            变量值=当前结果值,
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
