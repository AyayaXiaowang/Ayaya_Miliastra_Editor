"""
graph_id: server_signal_all_types_example_01
graph_name: 模板示例_信号全类型_发送与监听
graph_type: server
description: 示例节点图（信号参数类型演示）：使用信号 `测试信号_全部参数类型` 演示【发送信号】与【监听信号】的参数绑定写法。实体创建时发送一次信号（携带整数/浮点数/字符串/三维向量/布尔值/GUID/实体/配置ID/元件ID/整数列表），监听端在回调中对每个参数做中文类型注解并累加触发次数，便于验证端口补全与类型校验。
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
        name="调试_信号触发次数",
        variable_type="整数",
        default_value=0,
        description="记录本图中监听到测试信号的次数，方便在编辑器中观察。",
        is_exposed=False,
    ),
]

class 模板示例_信号全类型_发送与监听:
    """演示信号系统“多参数类型”的示例节点图。

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
        """实体创建完毕后，构造一次携带多种参数类型的示例信号并发送。"""
        自身实体: "实体" = 获取自身实体(self.game)

        三维向量示例值: "三维向量" = (1.0, 2.0, 3.0)

        布尔值示例值: "布尔值" = True

        整数列表示例值: "整数列表" = [1, 2, 3]

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
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        整数参数: "整数",
        浮点数参数: "浮点数",
        字符串参数: "字符串",
        三维向量参数: "三维向量",
        布尔值参数: "布尔值",
        GUID参数: "GUID",
        实体参数: "实体",
        配置ID参数: "配置ID",
        元件ID参数: "元件ID",
        整数列表参数: "整数列表",
    ) -> None:
        """当监听到测试信号时，累加触发次数。"""

        当前触发次数: "整数" = 获取节点图变量(
            self.game,
            变量名="调试_信号触发次数",
        )
        新触发次数: "整数" = 当前触发次数 + 1
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
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))
