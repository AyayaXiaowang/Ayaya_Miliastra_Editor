"""
graph_id: server_enum_coverage_status_end_reason_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_server_单位状态结束原因
graph_type: server
description: 枚举覆盖图（拆分版）：事件【单位状态结束时】的移除原因枚举候选项覆盖；每个事件 ≤ 20 节点。
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


class 校准_枚举覆盖_v1_server_单位状态结束原因:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    # ---------------------------- 事件：单位状态结束时 ----------------------------
    def on_单位状态结束时(
        self,
        事件源实体,
        事件源GUID,
        单位状态配置ID,
        施加者实体,
        持续时间是否无限,
        状态剩余时长,
        状态剩余层数,
        移除者实体,
        移除原因,
        槽位序号,
    ):
        __handle, __value = 获取局部变量(self.game, 初始值=False)
        设置局部变量(self.game, 局部变量=__handle, 值=__value)

        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=移除原因, 枚举2="其它单位状态顶替"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=移除原因, 枚举2="超出持续时间"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=移除原因, 枚举2="被驱散"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=移除原因, 枚举2="状态失效"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=移除原因, 枚举2="职业变更"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=移除原因, 枚举2="词条失效"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=移除原因, 枚举2="护盾含量归零"))

        return

    def register_handlers(self):
        self.game.register_event_handler("单位状态结束时", self.on_单位状态结束时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))


