"""
graph_id: server_template_multi_pedals_open_door_receiver_01
graph_name: 模板示例_多踏板同时按下_开门_接收端
graph_type: server
description: 示例节点图（多踏板同时按下开门：接收端）：仅处理 GUID 白名单内踏板广播的 `通用踏板开关_状态变化(是否激活=...)`；维护“当前激活踏板 GUID 列表”并计数；当激活数量达到阈值后开启大门，并对当时仍处于激活状态的踏板回发 `通用踏板开关_激活确认`，用于一次性踏板锁定按下并禁用触发器。
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
        name="踏板GUID列表",
        variable_type="GUID列表",
        default_value=[],
        description="对外暴露：踏板实体 GUID 白名单列表（仅接收该列表内踏板的“状态变化”信号）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="需要激活数量",
        variable_type="整数",
        default_value=1,
        description="对外暴露：要求同时处于激活状态的踏板数量阈值（1 也支持）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="门上升距离",
        variable_type="浮点数",
        default_value=3.0,
        description="对外暴露：大门开启时沿自身向上方向移动的距离。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="门上升速度",
        variable_type="浮点数",
        default_value=2.0,
        description="对外暴露：大门开启运动速度。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="当前激活踏板GUID列表",
        variable_type="GUID列表",
        default_value=[],
        description="内部缓存：当前处于激活状态的踏板 GUID 列表（用于计数与回发确认）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="当前激活数量",
        variable_type="整数",
        default_value=0,
        description="内部缓存：当前处于激活状态的踏板数量（等于“当前激活踏板GUID列表”的长度）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="门是否已打开",
        variable_type="布尔值",
        default_value=False,
        description="大门是否已经打开，用于避免重复开门与重复回发确认。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="门原始位置",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="记录大门初始位置。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="门原始旋转",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="记录大门初始旋转。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="门打开目标位置",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="大门打开后的目标位置。",
        is_exposed=False,
    ),
]

class 模板示例_多踏板同时按下_开门_接收端:
    """多踏板联动开门（接收端，可配置任意数量踏板，1 也支持）：

    - 监听 `通用踏板开关_状态变化`，通过监听事件自带的 `信号来源实体` → `以实体查询GUID` 获取发送方 GUID；
    - 使用节点图变量 `踏板GUID列表` 做白名单过滤，仅处理目标踏板集合的信号；
    - 使用节点图变量 `当前激活踏板GUID列表` 维护“当前处于激活状态的踏板集合”，并以其长度作为激活计数；
    - 当激活计数达到 `需要激活数量` 阈值后，开启大门定点运动器，并对“当时处于激活状态”的踏板回发 `通用踏板开关_激活确认`：
      若踏板配置为一次性，将锁定按下并禁用触发器，不再回弹。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """缓存大门原始位置/旋转，并预计算打开目标位置；同时初始化激活计数与状态。"""
        自身实体: "实体" = 获取自身实体(self.game)
        原始位置, 原始旋转 = 获取实体位置与旋转(
            self.game,
            目标实体=自身实体,
        )
        原始位置: "三维向量"
        原始旋转: "三维向量"

        设置节点图变量(
            self.game,
            变量名="门原始位置",
            变量值=原始位置,
            是否触发事件=False,
        )
        设置节点图变量(
            self.game,
            变量名="门原始旋转",
            变量值=原始旋转,
            是否触发事件=False,
        )

        门上升距离: "浮点数" = 获取节点图变量(
            self.game,
            变量名="门上升距离",
        )
        向上向量: "三维向量" = 获取实体向上向量(
            self.game,
            目标实体=自身实体,
        )
        位移向量: "三维向量" = 向上向量 * 门上升距离
        目标位置: "三维向量" = 原始位置 + 位移向量
        设置节点图变量(
            self.game,
            变量名="门打开目标位置",
            变量值=目标位置,
            是否触发事件=False,
        )

    # ---------------------------- 事件：监听踏板状态信号 ----------------------------
    def on_通用踏板开关_状态变化(
        self,
        事件源实体,
        事件源GUID,
        信号来源实体,
        是否激活,
    ):
        """按 GUID 白名单过滤踏板信号，用激活列表长度做计数，满足阈值后开门并回发确认。"""
        门是否已打开: "布尔值" = 获取节点图变量(
            self.game,
            变量名="门是否已打开",
        )
        if 门是否已打开:
            return

        目标踏板GUID列表: "GUID列表" = 获取节点图变量(
            self.game,
            变量名="踏板GUID列表",
        )
        来源GUID: "GUID" = 以实体查询GUID(
            self.game,
            实体=信号来源实体,
        )
        if 来源GUID in 目标踏板GUID列表:
            pass
        else:
            return

        当前激活踏板GUID列表: "GUID列表" = 获取节点图变量(
            self.game,
            变量名="当前激活踏板GUID列表",
        )
        是否已在激活列表: "布尔值" = 来源GUID in 当前激活踏板GUID列表

        # 维护“当前激活踏板GUID列表”：激活时追加（避免重复），失活时按序号移除
        是否激活_布尔值: "布尔值" = 是否激活
        if 是否激活_布尔值:
            if 是否已在激活列表:
                pass
            else:
                当前激活踏板GUID列表.append(来源GUID)
        else:
            if 是否已在激活列表:
                来源序号列表: "整数列表" = 查找列表并返回值的序号(
                    目标列表=当前激活踏板GUID列表,
                    值=来源GUID,
                )
                移除序号: "整数" = 来源序号列表[0]
                del 当前激活踏板GUID列表[移除序号]

        更新后激活数量: "整数" = len(当前激活踏板GUID列表)
        设置节点图变量(
            self.game,
            变量名="当前激活踏板GUID列表",
            变量值=当前激活踏板GUID列表,
            是否触发事件=False,
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
        是否满足开门条件: "布尔值" = 更新后激活数量 >= 需要激活数量
        if 是否满足开门条件:
            设置节点图变量(
                self.game,
                变量名="门是否已打开",
                变量值=True,
                是否触发事件=False,
            )

            # 开门：开启定点运动器（向上移动到目标位置）
            门打开目标位置: "三维向量" = 获取节点图变量(
                self.game,
                变量名="门打开目标位置",
            )
            门原始旋转: "三维向量" = 获取节点图变量(
                self.game,
                变量名="门原始旋转",
            )
            门上升速度: "浮点数" = 获取节点图变量(
                self.game,
                变量名="门上升速度",
            )

            自身实体_开门: "实体" = 获取自身实体(self.game)
            停止并删除基础运动器(
                self.game,
                目标实体=自身实体_开门,
                运动器名称="大门定点运动",
                是否停止所有基础运动器=False,
            )
            开启定点运动器(
                self.game,
                目标实体=自身实体_开门,
                运动器名称="大门定点运动",
                移动方式="匀速直线运动",
                移动速度=门上升速度,
                目标位置=门打开目标位置,
                目标旋转=门原始旋转,
                是否锁定旋转=True,
                参数类型="固定速度",
                移动时间=0.0,
            )

            # 回发确认：只对“当时处于激活状态”的踏板发送确认，避免锁定未被踩下的踏板
            for 当前激活踏板GUID in 当前激活踏板GUID列表:
                发送信号(
                    self.game,
                    信号名="通用踏板开关_激活确认",
                    开关GUID=当前激活踏板GUID,
                    是否允许锁定=True,
                )

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "通用踏板开关_状态变化",
            self.on_通用踏板开关_状态变化,
            owner=self.owner_entity,
        )

if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))
