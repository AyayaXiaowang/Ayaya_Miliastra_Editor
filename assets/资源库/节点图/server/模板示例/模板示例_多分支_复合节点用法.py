"""
graph_id: server_composite_multibranch_example_01
graph_name: 模板示例_多分支_复合节点用法
graph_type: server
description: 基础示例：在“实体创建时”调用多分支示例复合节点，根据随机整数从不同流程出口流出，并在 Graph Code 中使用 match self.多分支示例复合节点.按整数多分支(...) 的写法，将多个流程出口连接到不同的后续逻辑或调试显示。
"""

from __future__ import annotations

import sys
import pathlib

脚本文件路径 = pathlib.Path(__file__).resolve()
服务器节点图目录 = 脚本文件路径.parent.parent
if str(服务器节点图目录) not in sys.path:
    sys.path.insert(0, str(服务器节点图目录))

from _prelude import *
from engine.graph.models.package_model import GraphVariableConfig
from 资源库.复合节点库.composite_多分支_示例_类格式 import 多分支_示例_类格式


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_最后一次分支值",
        variable_type="整数",
        default_value=0,
        description="最近一次调用多分支示例复合节点时传入的分支值，便于在节点图变量面板中观察。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_最近分支标签",
        variable_type="字符串",
        default_value="未触发",
        description="最近一次调用多分支示例复合节点时命中的分支标签（建议在编辑器中将复合节点的数据输出“命中分支标签”连接到【设置节点图变量】节点并写入该变量）。",
        is_exposed=False,
    ),
]


class 模板示例_多分支_复合节点用法:
    """演示如何在普通节点图中复用“多分支_示例_类格式”复合节点，并在宿主图中显式使用其多个流程出口。

    流程说明：
    1. 在构造函数中实例化 `多分支_示例_类格式` 复合节点，作为本图的一个“子节点”。
    2. 在【实体创建时】事件中：
       - 生成 0~3 的随机整数作为分支值；
       - 将该值写入图变量“调试_最后一次分支值”；
       - 使用 `match self.多分支示例复合节点.按整数多分支(分支值=分支值)`，根据复合节点的不同流程出口（“分支为0/分支为1/分支为其他”）分别执行不同的后续逻辑，并写入图变量“调试_最近分支标签”。
    3. 在编辑器中加载本图时，可以直观看到复合节点在宿主图中作为一个多流程出口节点存在，各分支出口分别连到对应的后续节点，实现类似内置【多分支】节点的效果。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        # 实例化多分支示例复合节点，供后续事件中调用
        self.多分支示例复合节点 = 多分支_示例_类格式(game, owner_entity)

        from runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """实体创建完毕后，随机生成一个分支值并调用多分支示例复合节点。"""
        分支值: "整数" = 获取随机整数(self.game, 下限=0, 上限=3)

        # 记录最近一次调用时使用的分支值
        设置节点图变量(
            self.game,
            变量名="调试_最后一次分支值",
            变量值=分支值,
            是否触发事件=False,
        )

        # 使用 match + 复合节点调用，将不同流程出口接到不同的后续逻辑
        match self.多分支示例复合节点.按整数多分支(
            分支值=分支值,
        ):
            case "分支为0":
                设置节点图变量(
                    self.game,
                    变量名="调试_最近分支标签",
                    变量值="分支为0",
                    是否触发事件=False,
                )
            case "分支为1":
                设置节点图变量(
                    self.game,
                    变量名="调试_最近分支标签",
                    变量值="分支为1",
                    是否触发事件=False,
                )
            case "分支为其他":
                设置节点图变量(
                    self.game,
                    变量名="调试_最近分支标签",
                    变量值="分支为其他",
                    是否触发事件=False,
                )

    def register_handlers(self):
        """注册所有事件处理器。"""
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from runtime.engine.node_graph_validator import validate_file

    自身文件路径 = pathlib.Path(__file__).resolve()
    是否通过, 错误列表, 警告列表 = validate_file(自身文件路径)
    print("=" * 80)
    print(f"节点图自检: {自身文件路径.name}")
    print(f"文件: {自身文件路径}")
    if 是否通过:
        print("结果: 通过")
    else:
        print(f"结果: 未通过（错误: {len(错误列表)}，警告: {len(警告列表)}）")
        if 错误列表:
            print("\n错误明细:")
            for 序号, 错误文本 in enumerate(错误列表, start=1):
                print(f"  [{序号}] {错误文本}")
        if 警告列表:
            print("\n警告明细:")
            for 序号, 警告文本 in enumerate(警告列表, start=1):
                print(f"  [{序号}] {警告文本}")
    print("=" * 80)
    if not 是否通过:
        sys.exit(1)



