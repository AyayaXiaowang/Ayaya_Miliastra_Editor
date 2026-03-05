"""
graph_id: server_enum_coverage_entity_destroy_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_server_level
graph_type: server
mount_entity_type: 关卡
description: 自动生成枚举覆盖图：仅覆盖事件节点【实体销毁时】的输出枚举候选项（该图需挂载关卡实体）。
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


class 校准_枚举覆盖_v1_server_level:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体销毁时 ----------------------------
    def on_实体销毁时(
        self,
        事件源实体,
        事件源GUID,
        位置,
        朝向,
        实体类型,
        阵营,
        伤害来源,
        归属者实体,
        自定义变量组件快照,
    ):
        __handle, __value = 获取局部变量(self.game, 初始值=False)
        设置局部变量(self.game, 局部变量=__handle, 值=__value)
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=实体类型, 枚举2="实体类型_关卡"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=实体类型, 枚举2="实体类型_物件"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=实体类型, 枚举2="实体类型_玩家"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=实体类型, 枚举2="实体类型_角色"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=实体类型, 枚举2="实体类型_造物"))
        return

    def register_handlers(self):
        self.game.register_event_handler("实体销毁时", self.on_实体销毁时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))


