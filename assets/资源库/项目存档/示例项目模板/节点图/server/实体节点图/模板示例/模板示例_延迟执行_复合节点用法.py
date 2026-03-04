"""
graph_id: server_delay_composite_example_01
graph_name: 模板示例_延迟执行_复合节点用法
graph_type: server
description: 示例节点图（复合节点：延迟执行）：在【实体创建时】调用“延迟执行示例复合节点”为自身实体启动一次定时器；通过节点图变量记录是否已启动延迟流程，便于在编辑器中观察复合节点复用与延迟触发。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir()))
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / 'assets'))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403

from 资源库.项目存档.示例项目模板.复合节点库.composite_延迟执行_示例_类格式 import 延迟执行_示例_类格式

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_是否已启动延迟",
        variable_type="布尔值",
        default_value=False,
        description="用于标记本图是否已经为当前实体启动过一次延迟执行示例复合节点，便于在编辑器中观察。",
        is_exposed=False,
    ),
]

class 模板示例_延迟执行_复合节点用法:
    """演示如何在普通节点图中复用延迟执行示例复合节点。

    流程说明：
    1. 在构造函数中实例化 `延迟执行_示例_类格式` 复合节点，作为本图的一个“子节点”。
    2. 在【实体创建时】事件中：
       - 获取自身实体；
       - 将图变量“调试_是否已启动延迟”置为 True，表示已经触发过一次示例流程；
       - 调用复合节点的流程入口方法 `延迟执行`，为自身实体启动一个 N 秒后的定时器。
    3. 定时器触发时，复合节点内部会在其子图中从“触发完成”流程出口继续流转，后续可以在编辑器中为该出口连接其他逻辑。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        # 实例化延迟执行示例复合节点，供后续事件中调用
        # 注意：复合节点实例属性名需能被 IR 识别并映射到复合节点定义（建议包含复合节点类名）
        self.延迟执行_示例_类格式 = 延迟执行_示例_类格式(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """实体创建完毕后，为自身实体启动一次延迟执行示例复合节点。"""
        # 标记已启动过一次延迟流程，便于在图变量面板中观察
        设置节点图变量(
            self.game,
            变量名="调试_是否已启动延迟",
            变量值=True,
            是否触发事件=False,
        )

        # 调用复合节点的流程入口：为自身实体启动一个 2 秒后的定时器
        self.延迟执行_示例_类格式.延迟执行(
            目标实体=获取自身实体(self.game),
            延迟秒数=2.0,
            定时器标识="模板示例_延迟执行_复合节点用法",
        )

        设置节点图变量(
            self.game,
            变量名="调试_是否已启动延迟",
            变量值=True,
            是否触发事件=False,
        )

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )

if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))
