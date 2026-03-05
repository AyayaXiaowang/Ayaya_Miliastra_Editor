"""
graph_id: client_enum_coverage_camera_and_filter_rules_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_client_镜头检测与筛选规则
graph_type: client
description: 枚举覆盖图（拆分版）：覆盖筛选规则相关的输入枚举候选项；每个事件 ≤ 20 节点。
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

from app.runtime.engine.graph_prelude_client import *  # noqa: F401,F403

GRAPH_VARIABLES: list[GraphVariableConfig] = []


class 校准_枚举覆盖_v1_client_镜头检测与筛选规则:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    def on_节点图开始(self):
        占位_三维向量: "三维向量" = 创建三维向量(self.game, X分量=1.25, Y分量=2.50, Z分量=3.75)

        节点图开始(self.game)

        # --- 筛选规则（3） ---
        __方形_默认 = 筛选方形范围内的实体列表(
            self.game,
            宽度=1.0,
            高度=1.0,
            长度=1.0,
            中心位置=占位_三维向量,
            筛选数量上限=10,
            筛选规则="默认排序",
        )
        __方形_随机 = 筛选方形范围内的实体列表(
            self.game,
            宽度=1.0,
            高度=1.0,
            长度=1.0,
            中心位置=占位_三维向量,
            筛选数量上限=10,
            筛选规则="随机排序",
        )
        __方形_近远 = 筛选方形范围内的实体列表(
            self.game,
            宽度=1.0,
            高度=1.0,
            长度=1.0,
            中心位置=占位_三维向量,
            筛选数量上限=10,
            筛选规则="从近到远排序",
        )

        return

    def register_handlers(self):
        return


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))


