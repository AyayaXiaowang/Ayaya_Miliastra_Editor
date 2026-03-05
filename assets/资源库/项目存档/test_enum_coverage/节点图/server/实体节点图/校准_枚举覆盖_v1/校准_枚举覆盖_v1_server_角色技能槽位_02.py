"""
graph_id: server_enum_coverage_skill_slot_part02_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_server_角色技能槽位_02
graph_type: server
description: 枚举覆盖图（拆分版）：角色技能槽位枚举候选项覆盖（第 2 部分）；每个事件 ≤ 20 节点。
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


class 校准_枚举覆盖_v1_server_角色技能槽位_02:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        初始化角色技能(self.game, 目标实体=事件源实体, 角色技能槽位="自定义技能槽位6")
        初始化角色技能(self.game, 目标实体=事件源实体, 角色技能槽位="自定义技能槽位7")
        初始化角色技能(self.game, 目标实体=事件源实体, 角色技能槽位="自定义技能槽位8")
        初始化角色技能(self.game, 目标实体=事件源实体, 角色技能槽位="自定义技能槽位9")
        初始化角色技能(self.game, 目标实体=事件源实体, 角色技能槽位="自定义技能槽位10")
        初始化角色技能(self.game, 目标实体=事件源实体, 角色技能槽位="自定义技能槽位11")
        初始化角色技能(self.game, 目标实体=事件源实体, 角色技能槽位="自定义技能槽位12")
        初始化角色技能(self.game, 目标实体=事件源实体, 角色技能槽位="自定义技能槽位13")
        初始化角色技能(self.game, 目标实体=事件源实体, 角色技能槽位="自定义技能槽位14")
        初始化角色技能(self.game, 目标实体=事件源实体, 角色技能槽位="自定义技能槽位15")

        return

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))


