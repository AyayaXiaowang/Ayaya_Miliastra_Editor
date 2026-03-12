"""
graph_id: server_ts_writeback_bool_pins_01
graph_name: TS_写回回归_布尔值端口映射
graph_type: server
description: 写回回归：覆盖多类带布尔输入的节点，确保 `.gil` 写回/导出后布尔常量不翻转、不丢失、不发生端口错位。

每个节点至少包含一组 True 与一组 False，便于在 `.gil payload` Graph IR 中做对照。
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
INT_ONE = 1
CHAT_CHANNEL_INDEX_DEFAULT = 0

CUSTOM_VAR_NAME_TRUE = "回归_bool_custom_true"
CUSTOM_VAR_NAME_FALSE = "回归_bool_custom_false"

# 约束：节点图变量名长度 <= 20（validator: CODE_GRAPH_VAR_NAME_TOO_LONG）
GRAPH_VAR_NAME_TRUE = "回归_bool_gv_T"
GRAPH_VAR_NAME_FALSE = "回归_bool_gv_F"


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name=GRAPH_VAR_NAME_TRUE,
        variable_type="布尔值",
        default_value=False,
        description="回归用：布尔图变量（True 路径会写入 True）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name=GRAPH_VAR_NAME_FALSE,
        variable_type="布尔值",
        default_value=True,
        description="回归用：布尔图变量（False 路径会写入 False）。",
        is_exposed=True,
    ),
]


class TS_写回回归_布尔值端口映射:
    """布尔常量写回与端口映射回归图（server）。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # ============================================================================
        # 1) 自定义变量：是否触发事件（历史问题：真源存在双 Bol 槽位）
        # ============================================================================
        设置自定义变量(
            self.game,
            目标实体=事件源实体,
            变量名=CUSTOM_VAR_NAME_TRUE,
            变量值=INT_ONE,
            是否触发事件=True,
        )
        设置自定义变量(
            self.game,
            目标实体=事件源实体,
            变量名=CUSTOM_VAR_NAME_FALSE,
            变量值=INT_ONE,
            是否触发事件=False,
        )

        # ============================================================================
        # 2) 节点图变量：是否触发事件（对照：Set_Node_Graph_Variable 只有单 Bol）
        # ============================================================================
        设置节点图变量(
            self.game,
            变量名=GRAPH_VAR_NAME_TRUE,
            变量值=True,
            是否触发事件=True,
        )
        设置节点图变量(
            self.game,
            变量名=GRAPH_VAR_NAME_FALSE,
            变量值=False,
            是否触发事件=False,
        )

        # ============================================================================
        # 3) 常见“开关类”执行节点（仅覆盖 Bool InParam 常量写回，不追求运行期语义）
        # ============================================================================
        激活关闭模型显示(self.game, 目标实体=事件源实体, 是否激活=True)
        激活关闭模型显示(self.game, 目标实体=事件源实体, 是否激活=False)

        激活关闭原生碰撞(self.game, 目标实体=事件源实体, 是否激活=True)
        激活关闭原生碰撞(self.game, 目标实体=事件源实体, 是否激活=False)

        允许禁止玩家复苏(self.game, 玩家实体=事件源实体, 是否允许=True)
        允许禁止玩家复苏(self.game, 玩家实体=事件源实体, 是否允许=False)

        设置聊天频道开关(
            self.game,
            频道索引=CHAT_CHANNEL_INDEX_DEFAULT,
            文字开关=True,
            语音开关=True,
        )
        设置聊天频道开关(
            self.game,
            频道索引=CHAT_CHANNEL_INDEX_DEFAULT,
            文字开关=False,
            语音开关=False,
        )

        return

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

