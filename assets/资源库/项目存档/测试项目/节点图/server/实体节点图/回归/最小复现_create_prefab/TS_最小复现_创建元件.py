"""
graph_id: server_ts_min_repro_create_prefab_01
graph_name: TS_最小复现_创建元件
graph_type: server
description: 最小复现：实体创建触发 → 创建元件（端口索引一致性与写回/导入口径回归）。

- 元件ID 由图变量暴露：方便在不同存档中手动替换为可见元件ID
- 位置/旋转使用常量（避免连线引入额外节点干扰）
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


# ---------------------------- 常量（避免魔法数字） ----------------------------
ZERO_FLOAT = 0.0

POS_X = ZERO_FLOAT
POS_Y = ZERO_FLOAT
POS_Z = ZERO_FLOAT

ROT_X = ZERO_FLOAT
ROT_Y = ZERO_FLOAT
ROT_Z = ZERO_FLOAT

LEVEL_DEFAULT = 1
DO_NOT_OVERRIDE_LEVEL = False

EMPTY_TAG_INDEX_LIST: tuple[int, ...] = ()

GRAPH_VAR_PREFAB_ID_NAME = "测试_元件ID"


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name=GRAPH_VAR_PREFAB_ID_NAME,
        variable_type="元件ID",
        # 约束：元件ID 的 default_value 必须是可静态解析的 1~10 位纯数字（int 或数字字符串），不可引用变量常量。
        default_value=0,
        description="测试用：用于【创建元件】节点的元件ID；请在目标存档中改成一个可见元件ID。",
        is_exposed=True,
    ),
]


class TS_最小复现_创建元件:
    """创建元件（Create_Prefab）最小复现图（server）。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 注意：变量名必须是“可静态解析的字符串字面量”，否则代码规范校验无法将其对齐到 GRAPH_VARIABLES。
        prefab_id: "元件ID" = 获取节点图变量(self.game, 变量名="测试_元件ID")

        # 注意：最小复现图里避免使用 tuple 字面量构造 Vec3（部分链路会退化为未填参的“创建三维向量”节点）。
        pos: "三维向量" = 创建三维向量(self.game, X分量=POS_X, Y分量=POS_Y, Z分量=POS_Z)
        rot: "三维向量" = 创建三维向量(self.game, X分量=ROT_X, Y分量=ROT_Y, Z分量=ROT_Z)

        _spawned: "实体" = 创建元件(
            self.game,
            元件ID=prefab_id,
            位置=pos,
            旋转=rot,
            拥有者实体=事件源实体,
            是否覆写等级=DO_NOT_OVERRIDE_LEVEL,
            等级=LEVEL_DEFAULT,
            单位标签索引列表=EMPTY_TAG_INDEX_LIST,
        )
        return

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

