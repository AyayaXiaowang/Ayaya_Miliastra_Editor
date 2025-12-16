"""
graph_id: server_template_local_variable_counter
graph_name: 模板示例_局部变量计数
graph_type: server
description: 基础示例：在“实体创建时”摇随机数，命中 1 三次即退出循环，演示【获取局部变量→设置局部变量】的计数用法

节点图变量：
- 命中记录次数: 整数 = 0
- 最近一次摇值: 整数 = 0
"""

import sys
import pathlib

脚本文件路径 = pathlib.Path(__file__).resolve()
服务器节点图目录 = 脚本文件路径.parent.parent
if str(服务器节点图目录) not in sys.path:
    sys.path.insert(0, str(服务器节点图目录))

from _prelude import *
from engine.graph.models.package_model import GraphVariableConfig

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
    """演示局部变量节点的最小流程：

    1. 使用【获取局部变量(初始值=0)】拿到局部计数器句柄与当前值；
    2. 在循环内当检测到随机数为 1 时累加，用【设置局部变量】回写；
    3. 当命中次数达到 3 次后立即退出循环，并把结果写入节点图变量，方便 UI 观察。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        命中计数句柄, 当前命中次数 = 获取局部变量(self.game, 初始值=0)
        最近一次摇值句柄, 最近一次摇值 = 获取局部变量(self.game, 初始值=0)
        for 轮次索引 in range(0, 30):
            最近一次摇值: "整数" = 获取随机整数(self.game, 下限=0, 上限=2)
            设置局部变量(self.game, 局部变量=最近一次摇值句柄, 值=最近一次摇值)

            命中一次 = 是否相等(self.game, 枚举1=最近一次摇值, 枚举2=1)
            if 命中一次:
                当前命中次数: "整数" = 加法运算(self.game, 左值=当前命中次数, 右值=1)
                设置局部变量(self.game, 局部变量=命中计数句柄, 值=当前命中次数)

                达到退出条件 = 数值大于等于(self.game, 左值=当前命中次数, 右值=3)
                if 达到退出条件:
                    break

        设置节点图变量(self.game, 变量名="命中记录次数", 变量值=当前命中次数, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="最近一次摇值", 变量值=最近一次摇值, 是否触发事件=False)

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file

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

