"""
graph_id: server_composite_many_pins_example_01
graph_name: 模板示例_多引脚_复合节点用法
graph_type: server
description: 示例节点图（复合节点：多引脚）：调用“多引脚模板_包装_单入口_示例”复合节点，覆盖多数据入/出 + 多流程出口在导出 .gia 时的引脚/映射稳定性。
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

from 资源库.项目存档.示例项目模板.复合节点库.composite_多引脚模板_包装_单入口_示例 import 多引脚模板_包装_单入口_示例


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_多引脚_最近分支标签",
        variable_type="字符串",
        default_value="未触发",
        description="最近一次调用多引脚复合节点时命中的流程分支标签（正向/非正向）。",
        is_exposed=False,
    ),
]


class 模板示例_多引脚_复合节点用法:
    """在宿主图中调用“多引脚模板_包装_单入口_示例”复合节点，并把其多个流程出口分别连到不同逻辑。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        # 复合节点实例：属性名建议包含复合节点类名，便于解析器稳定识别
        self.多引脚模板_包装_单入口_示例 = 多引脚模板_包装_单入口_示例(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        match self.多引脚模板_包装_单入口_示例.执行一次组合流程(
            输入数值A=1.5,
            输入数值B=-0.25,
            说明文本="多引脚复合节点导出测试",
            输入列表=[1, 2, 3],
            默认整数=0,
        ):
            case "正向分支":
                设置节点图变量(
                    self.game,
                    变量名="调试_多引脚_最近分支标签",
                    变量值="正向分支",
                    是否触发事件=False,
                )
            case "非正向分支":
                设置节点图变量(
                    self.game,
                    变量名="调试_多引脚_最近分支标签",
                    变量值="非正向分支",
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

