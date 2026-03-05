"""
graph_id: server_enum_coverage_bag_item_change_reason_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_server_背包道具变化原因
graph_type: server
description: 枚举覆盖图（拆分版）：事件【背包道具数量变化时】的变化原因枚举候选项覆盖；每个事件 ≤ 20 节点。
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


class 校准_枚举覆盖_v1_server_背包道具变化原因:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    # ---------------------------- 事件：背包道具数量变化时 ----------------------------
    def on_背包道具数量变化时(self, 道具持有者实体, 道具持有者GUID, 道具配置ID, 变化前数量, 变化后数量, 变化原因):
        __handle, __value = 获取局部变量(self.game, 初始值=False)
        设置局部变量(self.game, 局部变量=__handle, 值=__value)

        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=变化原因, 枚举2="销毁"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=变化原因, 枚举2="丢弃"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=变化原因, 枚举2="使用"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=变化原因, 枚举2="被击倒掉落"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=变化原因, 枚举2="商店交易"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=变化原因, 枚举2="节点图操作"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=变化原因, 枚举2="拾取"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=变化原因, 枚举2="默认"))

        return

    def register_handlers(self):
        self.game.register_event_handler("背包道具数量变化时", self.on_背包道具数量变化时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))


