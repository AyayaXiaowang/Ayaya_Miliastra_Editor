"""
graph_id: server_signal_all_types_example_01
graph_name: 模板示例_信号全类型_发送与监听
graph_type: server
description: 使用 测试信号_全部参数类型 信号演示【发送信号】与【监听信号】的全参数类型用例：在实体创建时发送一次带全部参数的信号，并在监听事件中将各参数通过别名与调试变量串联，方便在编辑器中观测。

节点图变量：
- 调试_信号触发次数: 整数 = 0
"""

from __future__ import annotations

import sys
import pathlib

脚本文件路径 = pathlib.Path(__file__).resolve()
节点图根目录 = 脚本文件路径.parents[2]  # 节点图根目录（.../节点图）
服务器节点图目录 = 节点图根目录 / "server"  # 包含 server 侧 `_prelude.py` 的目录
if str(服务器节点图目录) not in sys.path:
    sys.path.insert(0, str(服务器节点图目录))

from _prelude import *
from engine.graph.models.package_model import GraphVariableConfig


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_信号触发次数",
        variable_type="整数",
        default_value=0,
        description="记录本图中监听到测试信号的次数，方便在编辑器中观察。",
        is_exposed=False,
    ),
]


class 模板示例_信号全类型_发送与监听:
    """演示信号系统全参数类型用法的模板示例。

    用法约定：
    - 本图挂载在任意可参与信号系统的实体上（例如关卡实体或控制终端实体）；
    - 在【实体创建时】事件中调用【发送信号】节点，向自身实体发送一次
      `测试信号_全部参数类型` 信号，并为每个参数类型提供示例值：
      - 标量：整数 / 浮点数 / 字符串 / 三维向量 / 布尔值 / GUID / 实体 / 配置ID / 元件ID；
      - 列表：示例中使用“整数列表参数”演示列表类型，其余列表类型可按需在其他信号中扩展。
    - 在【监听信号】事件中，按“事件源实体 / 事件源GUID / 信号来源实体 + 参数列表”的形态
      接收该信号，将所有参数通过类型注解的“纯别名赋值”串联一次，并维护
      `调试_信号触发次数` 变量，便于在编辑器中确认事件是否被正确触发。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """实体创建完毕后，构造一次覆盖全部参数类型的示例信号并发送。"""
        自身实体: "实体" = 获取自身实体(self.game)

        三维向量示例值: "三维向量" = 创建三维向量(
            self.game,
            X分量=1.0,
            Y分量=2.0,
            Z分量=3.0,
        )

        布尔值示例值: "布尔值" = 是否相等(
            self.game,
            输入1=1,
            输入2=1,
        )

        整数列表示例值: "整数列表" = 拼装列表(
            self.game,
            1,
            2,
            3,
        )

        发送信号(
            self.game,
            信号名="测试信号_全部参数类型",
            整数参数=1,
            浮点数参数=1.5,
            字符串参数="示例字符串_全类型信号",
            三维向量参数=三维向量示例值,
            布尔值参数=布尔值示例值,
            GUID参数="123456789",
            实体参数=自身实体,
            配置ID参数=1001,
            元件ID参数=2001,
            整数列表参数=整数列表示例值,
        )

    # ---------------------------- 事件：监听信号 ----------------------------
    def on_监听信号(
        self,
        事件源实体,
        事件源GUID,
        信号来源实体,
        整数参数,
        浮点数参数,
        字符串参数,
        三维向量参数,
        布尔值参数,
        GUID参数,
        实体参数,
        配置ID参数,
        元件ID参数,
        整数列表参数,
    ):
        """当监听到测试信号时，通过“纯别名赋值”方式将全部参数类型串联一次，并累加触发次数。"""
        整数参数别名: "整数" = 整数参数
        浮点数参数别名: "浮点数" = 浮点数参数
        字符串参数别名: "字符串" = 字符串参数
        三维向量参数别名: "三维向量" = 三维向量参数
        布尔值参数别名: "布尔值" = 布尔值参数
        GUID参数别名: "GUID" = GUID参数
        实体参数别名: "实体" = 实体参数
        配置ID参数别名: "配置ID" = 配置ID参数
        元件ID参数别名: "元件ID" = 元件ID参数
        整数列表参数别名: "整数列表" = 整数列表参数

        当前触发次数: "整数" = 获取节点图变量(
            self.game,
            变量名="调试_信号触发次数",
        )
        新触发次数: "整数" = 加法运算(
            self.game,
            左值=当前触发次数,
            右值=1,
        )
        设置节点图变量(
            self.game,
            变量名="调试_信号触发次数",
            变量值=新触发次数,
            是否触发事件=False,
        )
        return

    # ---------------------------- 注册事件处理器 ----------------------------
    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )
        # 监听信号事件：事件名现在直接使用“信号名（显示名称）”，
        # 解析器会在构建 GraphModel 时将该名称解析为稳定的 signal_id 并写入
        # GraphModel.metadata["signal_bindings"]，从而驱动端口补全与类型校验。
        self.game.register_event_handler(
            "测试信号_全部参数类型",
            self.on_监听信号,
            owner=self.owner_entity,
        )


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


