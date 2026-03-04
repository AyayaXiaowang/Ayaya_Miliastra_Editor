"""
graph_id: server_test_composite_multi_pins_aux_flow_01
graph_name: 测试_复合节点_多引脚_辅助流程列表
graph_type: server
description: 回归用例：在宿主图中调用“多引脚模板_示例”的辅助流程入口，输入整数列表并通过 match-case 连接“列表非空/列表为空”两条流程出口，同时记录数据输出。
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
        name="调试_列表首元素",
        variable_type="整数",
        default_value=0,
        description="记录辅助流程输出的列表首元素。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_列表长度",
        variable_type="整数",
        default_value=0,
        description="记录辅助流程输出的列表长度。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_命中分支",
        variable_type="字符串",
        default_value="未触发",
        description="记录辅助流程命中的流程出口名称。",
        is_exposed=False,
    ),
]


class 测试_复合节点_多引脚_辅助流程列表:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        self.多引脚模板_包装_单入口_示例 = 多引脚模板_包装_单入口_示例(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        输入列表: "整数列表" = [3, 2, 1]

        列表首元素: "整数"
        列表长度: "整数"

        设置节点图变量(self.game, 变量名="调试_命中分支", 变量值="开始", 是否触发事件=False)

        match self.多引脚模板_包装_单入口_示例.执行一次组合流程(
            输入数值A=2.0,
            输入数值B=1.0,
            说明文本="测试_多引脚模板_主流程_占位",
            输入列表=输入列表,
            默认整数=99,
        ):
            case "正向分支":
                设置节点图变量(self.game, 变量名="调试_命中分支", 变量值="正向分支", 是否触发事件=False)
            case "非正向分支":
                设置节点图变量(self.game, 变量名="调试_命中分支", 变量值="非正向分支", 是否触发事件=False)

        # 便于观察：把“预期输出”写入变量（与复合节点内部语义一致）
        列表长度 = 获取列表长度(列表=输入列表)
        列表首元素 = 获取列表对应值(列表=输入列表, 序号=0)
        设置节点图变量(self.game, 变量名="调试_列表首元素", 变量值=列表首元素, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_列表长度", 变量值=列表长度, 是否触发事件=False)

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

