"""
graph_id: server_enum_coverage_part01_basic_inputs_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_server_01_基础输入
graph_type: server
description: 枚举覆盖图（拆分版）：仅展示一批常用输入枚举值的设置方式；每个事件控制在 20 个节点以内。
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

GRAPH_VARIABLES: list[GraphVariableConfig] = []


class 校准_枚举覆盖_v1_server:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        自身实体: "实体" = 获取自身实体(self.game)

        占位_整数列表: "整数列表" = [1, 2, 3]

        # --- 排序规则（顺序/逆序）：只需对一种列表类型演示即可 ---
        列表排序(self.game, 列表=占位_整数列表, 排序方式="排序规则_顺序")
        列表排序(self.game, 列表=占位_整数列表, 排序方式="排序规则_逆序")

        # --- 掉落类型（全员一份/每人一份）：只选择一个节点演示即可 ---
        触发战利品掉落(self.game, 掉落者实体=自身实体, 掉落类型="全员一份")
        触发战利品掉落(self.game, 掉落者实体=自身实体, 掉落类型="每人一份")

        # --- 扫描标签规则（视野优先/距离优先） ---
        设置扫描标签的规则(self.game, 目标实体=自身实体, 规则类型="视野优先")
        设置扫描标签的规则(self.game, 目标实体=自身实体, 规则类型="距离优先")

        # --- 伤害跳字类型（无/普通/暴击） ---
        损失生命(
            self.game,
            目标实体=自身实体,
            生命损失量=1.0,
            是否致命=False,
            是否可被无敌抵挡=False,
            是否可被锁定生命值抵挡=False,
            伤害跳字类型="无跳字",
        )
        损失生命(
            self.game,
            目标实体=自身实体,
            生命损失量=1.0,
            是否致命=False,
            是否可被无敌抵挡=False,
            是否可被锁定生命值抵挡=False,
            伤害跳字类型="普通跳字",
        )
        损失生命(
            self.game,
            目标实体=自身实体,
            生命损失量=1.0,
            是否致命=False,
            是否可被无敌抵挡=False,
            是否可被锁定生命值抵挡=False,
            伤害跳字类型="暴击跳字",
        )

        # --- 界面控件显示状态（关闭/开启/隐藏） ---
        修改界面布局内界面控件状态(self.game, 目标玩家=自身实体, 界面控件索引=1, 显示状态="界面控件组状态_关闭")
        修改界面布局内界面控件状态(self.game, 目标玩家=自身实体, 界面控件索引=1, 显示状态="界面控件组状态_开启")
        修改界面布局内界面控件状态(self.game, 目标玩家=自身实体, 界面控件索引=1, 显示状态="界面控件组状态_隐藏")

        # --- 卡牌选择器刷新方式（不可/部分/全量） ---
        唤起卡牌选择器(
            self.game,
            目标玩家=自身实体,
            卡牌选择器索引=1,
            选择时长=1.0,
            选择结果对应列表=占位_整数列表,
            选择显示对应列表=占位_整数列表,
            选择数量下限=1,
            选择数量上限=1,
            刷新方式="不可刷新",
            刷新数量下限=0,
            刷新数量上限=0,
            默认返回选择=占位_整数列表,
        )
        唤起卡牌选择器(
            self.game,
            目标玩家=自身实体,
            卡牌选择器索引=1,
            选择时长=1.0,
            选择结果对应列表=占位_整数列表,
            选择显示对应列表=占位_整数列表,
            选择数量下限=1,
            选择数量上限=1,
            刷新方式="部分刷新",
            刷新数量下限=0,
            刷新数量上限=0,
            默认返回选择=占位_整数列表,
        )

        return

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))



