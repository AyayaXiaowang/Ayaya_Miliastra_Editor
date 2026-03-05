"""
graph_id: client_enum_coverage_raycast_and_entity_type_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_client_射线检测与实体类型
graph_type: client
description: 枚举覆盖图（拆分版）：覆盖【获取射线检测结果】的阵营/实体类型输入枚举与命中层筛选枚举列表；每个事件 ≤ 20 节点。
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


class 校准_枚举覆盖_v1_client_射线检测与实体类型:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    def on_节点图开始(self):
        自身实体: "实体" = 获取自身实体(self.game)
        占位_三维向量: "三维向量" = 创建三维向量(self.game, X分量=1.25, Y分量=2.50, Z分量=3.75)
        阵营筛选_无: "枚举" = "无"

        # 命中层筛选为“枚举列表”（使用字面量列表承接每个候选值）
        命中层筛选_受击盒: "枚举列表" = ["受击盒"]
        命中层筛选_场景: "枚举列表" = ["场景"]
        命中层筛选_物件自身碰撞: "枚举列表" = ["物件自身碰撞"]

        节点图开始(self.game)

        __命中位置_0, __命中实体_0 = 获取射线检测结果(
            self.game,
            检测发起者实体=自身实体,
            出射位置=占位_三维向量,
            出射方向=占位_三维向量,
            射线最大长度=10.0,
            阵营筛选=阵营筛选_无,
            实体类型筛选="实体类型_关卡",
            命中层筛选=命中层筛选_受击盒,
        )
        __命中位置_1, __命中实体_1 = 获取射线检测结果(
            self.game,
            检测发起者实体=自身实体,
            出射位置=占位_三维向量,
            出射方向=占位_三维向量,
            射线最大长度=10.0,
            阵营筛选=阵营筛选_无,
            实体类型筛选="实体类型_物件",
            命中层筛选=命中层筛选_场景,
        )
        __命中位置_2, __命中实体_2 = 获取射线检测结果(
            self.game,
            检测发起者实体=自身实体,
            出射位置=占位_三维向量,
            出射方向=占位_三维向量,
            射线最大长度=10.0,
            阵营筛选=阵营筛选_无,
            实体类型筛选="实体类型_玩家",
            命中层筛选=命中层筛选_物件自身碰撞,
        )
        __命中位置_3, __命中实体_3 = 获取射线检测结果(
            self.game,
            检测发起者实体=自身实体,
            出射位置=占位_三维向量,
            出射方向=占位_三维向量,
            射线最大长度=10.0,
            阵营筛选=阵营筛选_无,
            实体类型筛选="实体类型_角色",
            命中层筛选=命中层筛选_受击盒,
        )
        __命中位置_4, __命中实体_4 = 获取射线检测结果(
            self.game,
            检测发起者实体=自身实体,
            出射位置=占位_三维向量,
            出射方向=占位_三维向量,
            射线最大长度=10.0,
            阵营筛选=阵营筛选_无,
            实体类型筛选="实体类型_造物",
            命中层筛选=命中层筛选_场景,
        )

        return

    def register_handlers(self):
        return


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))


