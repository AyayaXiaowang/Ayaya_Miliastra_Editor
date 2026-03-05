"""
graph_id: server_test_project_level7_door_controller
graph_name: 大门实体_第七关_门控制
graph_type: server
description: 第七关“大门”控制图（与 UI 回合流程解耦）：

- 监听单一信号：`第七关_门_动作(目标状态="打开"/"关闭")`
- 行为：
  - 实体创建时缓存门的关闭位姿并预计算打开位姿
  - 通过定点运动器控制门开关（匀速直线）
  - 门动作音效改为“发信号广播 → 玩家图播放”（解耦播放逻辑）
  - 关闭动作完成后广播 `第七关_门_关闭完成`（依赖 `基础运动器停止时` 事件）

注意：本图只负责“门本身”的动作与完成判定；关门完成后的业务推进（生成亲戚/进入结算等）由 UI 图处理。
- 挂载实体：门实体本身（需要挂在持有基础运动器组件的门上，才能稳定收到 `基础运动器停止时`）。
- 本图不使用定时器兜底：请确保门实体的基础运动器停止事件可用。
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


# 门动作：运动器
门运动器名称: "字符串" = "第七关_门_定点运动"

# 门动作音效（2D）：通过信号广播给玩家图播放
音量_满: "整数" = 100
播放速度_默认: "浮点数" = 1.0
音效_开门: "整数" = 50281


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    # ---------------------------- 门参数（对外暴露） ----------------------------
    GraphVariableConfig(
        name="门打开相对位移",
        variable_type="三维向量",
        default_value=(0.0, 2.0, 0.0),
        description="对外暴露：门从“关闭位置”移动到“打开位置”的相对位移（三维向量）。打开位置 = 关闭位置 + 位移。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="门移动速度",
        variable_type="浮点数",
        default_value=2.0,
        description="对外暴露：门开关时的匀速直线运动速度（用于定点运动器）。",
        is_exposed=True,
    ),
    # ---------------------------- 门内部状态 ----------------------------
    GraphVariableConfig(
        name="门_关闭位置",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="内部：门关闭位置（实体创建时缓存）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="门_打开位置",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="内部：门打开位置（在缓存关闭位置后预计算）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="门_原始旋转",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="内部：门初始旋转（锁定旋转时使用）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="门_运动目标状态",
        variable_type="字符串",
        default_value="无",
        description="内部：门当前预期运动完成状态：打开/关闭。",
        is_exposed=False,
    ),
]


class 大门实体_第七关_门控制:
    def __init__(self, game: GameRuntime, owner_entity: "实体"):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体: "实体", 事件源GUID: "GUID") -> None:
        门实体: "实体" = 事件源实体
        if 门实体 == self.owner_entity:
            pass
        else:
            return

        门位置: "三维向量"
        门旋转: "三维向量"
        门位置, 门旋转 = 获取实体位置与旋转(self.game, 目标实体=门实体)
        设置节点图变量(self.game, 变量名="门_关闭位置", 变量值=门位置, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="门_原始旋转", 变量值=门旋转, 是否触发事件=False)

        门偏移: "三维向量" = 获取节点图变量(self.game, 变量名="门打开相对位移")
        门打开位置: "三维向量" = 三维向量加法(self.game, 三维向量1=门位置, 三维向量2=门偏移)
        设置节点图变量(self.game, 变量名="门_打开位置", 变量值=门打开位置, 是否触发事件=False)
        return

    def on_第七关_门_动作(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        目标状态: "字符串",
    ) -> None:
        门实体2: "实体" = self.owner_entity
        目标旋转: "三维向量" = 获取节点图变量(self.game, 变量名="门_原始旋转")
        速度: "浮点数" = 获取节点图变量(self.game, 变量名="门移动速度")

        # 避免“停止旧运动器”触发停止事件导致误判：先清空目标状态，再停旧运动器
        设置节点图变量(self.game, 变量名="门_运动目标状态", 变量值="无", 是否触发事件=False)
        停止并删除基础运动器(
            self.game,
            目标实体=门实体2,
            运动器名称=门运动器名称,
            是否停止所有基础运动器=False,
        )

        # 开门
        if 目标状态 == "打开":
            目标位置: "三维向量" = 获取节点图变量(self.game, 变量名="门_打开位置")
            # 先标记目标状态，再启动运动器（确保同步触发 on_基础运动器停止时 时状态已就位）
            设置节点图变量(self.game, 变量名="门_运动目标状态", 变量值="打开", 是否触发事件=False)
            开启定点运动器(
                self.game,
                目标实体=门实体2,
                运动器名称=门运动器名称,
                移动方式="匀速直线运动",
                移动速度=速度,
                目标位置=目标位置,
                目标旋转=目标旋转,
                是否锁定旋转=True,
                参数类型="固定速度",
                移动时间=0.0,
            )

        # 关门
        elif 目标状态 == "关闭":
            目标位置: "三维向量" = 获取节点图变量(self.game, 变量名="门_关闭位置")
            # 先标记目标状态，再启动运动器（确保同步触发 on_基础运动器停止时 时状态已就位）
            设置节点图变量(self.game, 变量名="门_运动目标状态", 变量值="关闭", 是否触发事件=False)
            开启定点运动器(
                self.game,
                目标实体=门实体2,
                运动器名称=门运动器名称,
                移动方式="匀速直线运动",
                移动速度=速度,
                目标位置=目标位置,
                目标旋转=目标旋转,
                是否锁定旋转=True,
                参数类型="固定速度",
                移动时间=0.0,
            )
        else:
            return

        # 门动作音效：广播信号，由玩家实体挂载图接收并播放
        发送信号(self.game, 信号名="第七关_播放2D音效", 音效资产索引=音效_开门)
        return

    # ---------------------------- 事件：基础运动器停止时（用于门动作完成） ----------------------------
    def on_基础运动器停止时(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        运动器名称: "字符串",
    ) -> None:
        if 事件源实体 == self.owner_entity:
            pass
        else:
            return
        if 运动器名称 == 门运动器名称:
            目标状态: "字符串" = 获取节点图变量(self.game, 变量名="门_运动目标状态")
            if 目标状态 == "关闭":
                设置节点图变量(self.game, 变量名="门_运动目标状态", 变量值="无", 是否触发事件=False)
                发送信号(self.game, 信号名="第七关_门_关闭完成")
        return

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "第七关_门_动作",
            self.on_第七关_门_动作,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "基础运动器停止时",
            self.on_基础运动器停止时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

