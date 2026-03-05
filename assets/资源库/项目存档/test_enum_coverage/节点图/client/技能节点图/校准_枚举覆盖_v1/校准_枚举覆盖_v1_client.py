"""
graph_id: client_enum_coverage_part01_turn_and_disturbance_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_client_01_转向与扰动装置
graph_type: client
description: 枚举覆盖图（拆分版）：覆盖【玩家转向】与【移除指定角色扰动装置】的输入枚举候选项；每个事件 ≤ 20 节点。
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


class 校准_枚举覆盖_v1_client_01_转向与扰动装置:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    def on_节点图开始(self):
        # client 技能节点图入口
        节点图开始(self.game)

        # --- 玩家转向（6） ---
        玩家转向(self.game, 转向模式="先目标后输入")
        玩家转向(self.game, 转向模式="输入朝向")
        玩家转向(self.game, 转向模式="目标朝向")
        玩家转向(self.game, 转向模式="先目标后镜头")
        玩家转向(self.game, 转向模式="镜头朝向")
        玩家转向(self.game, 转向模式="先输入后目标")

        # --- 移除指定角色扰动装置（3） ---
        移除指定角色扰动装置(self.game, 扰动装置类型="扰动装置类型_力场器")
        移除指定角色扰动装置(self.game, 扰动装置类型="扰动装置类型_弹射器")
        移除指定角色扰动装置(self.game, 扰动装置类型="扰动装置类型_牵引器")

        return

    def register_handlers(self):
        # client 技能节点图由运行时统一调用 on_节点图开始，不需要显式 register_event_handler
        return


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))


