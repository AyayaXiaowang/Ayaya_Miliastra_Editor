"""
graph_id: server_multi_pedal_link_example_01
graph_name: 模板示例_多踏板联动
graph_type: server
description: 通过监听“通用踏板开关_状态变化”信号，将目标踏板集合（按 GUID 白名单过滤）的激活状态聚合为一个总开关；可配置需要同时激活的踏板数量，实现任意数量的多踏板联动。

节点图变量：
- 踏板GUID列表_变量名: 字符串 = "关联踏板GUID列表" [对外暴露]
- 需要激活数量: 整数 = 2 [对外暴露]
- 消息目标GUID列表_变量名: 字符串 = "关联实体GUID列表" [对外暴露]
- 消息触发变量名: 字符串 = "是否激活" [对外暴露]

- 当前激活数量: 整数 = 0
- 是否已激活: 布尔值 = False
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
        name="踏板GUID列表_变量名",
        variable_type="字符串",
        default_value="关联踏板GUID列表",
        description="对外暴露：用于读取“目标踏板 GUID 列表”的自定义变量名（通常挂在本图所属实体上），只统计该列表内的踏板信号。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="需要激活数量",
        variable_type="整数",
        default_value=2,
        description="对外暴露：要求同组踏板中至少有多少个处于激活状态时才视为“联动开门”。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="消息目标GUID列表_变量名",
        variable_type="字符串",
        default_value="关联实体GUID列表",
        description="对外暴露：用于读取目标实体 GUID 列表的自定义变量名（通常挂在本图所属实体上）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="消息触发变量名",
        variable_type="字符串",
        default_value="是否激活",
        description="对外暴露：向目标实体写入的布尔触发变量名，用于驱动大门等联动目标。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="当前激活数量",
        variable_type="整数",
        default_value=0,
        description="当前联动组内处于激活状态的踏板数量（通过信号增减统计）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="是否已激活",
        variable_type="布尔值",
        default_value=False,
        description="当前联动总开关是否处于“已激活”状态，用于避免重复写入目标实体变量。",
        is_exposed=False,
    ),
]


class 模板示例_多踏板联动:
    """多踏板联动示例：任意数量的踏板共同控制一组大门。

    用法说明：
    - 每个踏板使用 `模板示例_踏板开关_信号广播`，踏板端仅广播 `是否激活`；
    - 本图挂载在一个“联动控制器”实体上，该实体通过自定义变量保存：
      - 目标踏板 GUID 列表（用于过滤只处理这些踏板的信号）；
      - 要控制的大门 GUID 列表；
    - 当监听到 `通用踏板开关_状态变化` 信号时，通过监听事件自带的 `信号来源实体` 获取发送方 GUID，
      并仅在其属于“目标踏板 GUID 列表”时参与统计；然后根据 `是否激活` 对当前激活数量做 +1 / -1，
      在达到或失去联动条件时，为目标实体写入布尔变量（例如大门的“是否激活”），实现多踏板联动。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：监听踏板状态信号 ----------------------------
    def on_通用踏板开关_状态变化(
        self,
        事件源实体,
        事件源GUID,
        信号来源实体,
        是否激活: "布尔值",
    ):
        """监听踏板广播的“是否激活”状态，并按“目标踏板 GUID 列表”过滤后统计当前激活数量。"""
        踏板GUID列表_变量名: "字符串" = 获取节点图变量(
            self.game,
            变量名="踏板GUID列表_变量名",
        )
        目标踏板GUID列表: "GUID列表" = 获取自定义变量(
            self.game,
            目标实体=获取自身实体(self.game),
            变量名=踏板GUID列表_变量名,
        )
        来源GUID: "GUID" = 以实体查询GUID(
            self.game,
            实体=信号来源实体,
        )
        是否目标踏板: "布尔值" = 列表是否包含该值(
            self.game,
            列表=目标踏板GUID列表,
            值=来源GUID,
        )
        if 是否目标踏板:
            pass
        else:
            return

        当前激活数量: "整数" = 获取节点图变量(
            self.game,
            变量名="当前激活数量",
        )
        更新后激活数量: "整数"
        是否激活_布尔: "布尔值" = 是否激活
        if 是否激活_布尔:
            更新后激活数量 = 加法运算(
                self.game,
                左值=当前激活数量,
                右值=1,
            )
        else:
            更新后激活数量 = 减法运算(
                self.game,
                左值=当前激活数量,
                右值=1,
            )

        设置节点图变量(
            self.game,
            变量名="当前激活数量",
            变量值=更新后激活数量,
            是否触发事件=False,
        )

        需要激活数量: "整数" = 获取节点图变量(
            self.game,
            变量名="需要激活数量",
        )
        是否满足联动条件: "布尔值" = 数值大于等于(
            self.game,
            左值=更新后激活数量,
            右值=需要激活数量,
        )

        之前是否已激活: "布尔值" = 获取节点图变量(
            self.game,
            变量名="是否已激活",
        )
        是否状态发生变化: "布尔值" = 逻辑异或运算(
            self.game,
            输入1=是否满足联动条件,
            输入2=之前是否已激活,
        )
        if 是否状态发生变化:
            pass
        else:
            return

        # 记录新的联动总开关状态
        设置节点图变量(
            self.game,
            变量名="是否已激活",
            变量值=是否满足联动条件,
            是否触发事件=False,
        )

        # 将联动结果广播给目标实体（通常是一组大门）
        列表变量名_联动: "字符串" = 获取节点图变量(
            self.game,
            变量名="消息目标GUID列表_变量名",
        )
        目标变量名_联动: "字符串" = 获取节点图变量(
            self.game,
            变量名="消息触发变量名",
        )
        目标GUID列表_联动: "GUID列表" = 获取自定义变量(
            self.game,
            目标实体=获取自身实体(self.game),
            变量名=列表变量名_联动,
        )
        for 当前GUID_联动 in 目标GUID列表_联动:
            设置自定义变量(
                self.game,
                目标实体=以GUID查询实体(
                    self.game,
                    GUID=当前GUID_联动,
                ),
                变量名=目标变量名_联动,
                变量值=是否满足联动条件,
                是否触发事件=True,
            )

    def register_handlers(self):
        """注册监听踏板状态变化信号的事件处理器。"""
        self.game.register_event_handler(
            "通用踏板开关_状态变化",
            self.on_通用踏板开关_状态变化,
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


