"""
graph_id: server_regression_graph_mount_entity_01
graph_name: 回归_节点图挂载_实体
graph_type: server
mount: entity_key:一个有节点图的空模型
description: 最小回归：导出/写回时将节点图挂载写入 base .gil 的实体摆放段（root5，slot=3）。
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
LEFT_VALUE = 1
RIGHT_VALUE = 2
ZERO_VALUE = 0


class 回归_节点图挂载_实体:
    def __init__(self, game, owner_entity):
        # 初始化节点图并做静态校验。
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 实体创建事件回调：执行一次最小节点调用。
        _结果: "整数" = 加法运算(self.game, 左值=LEFT_VALUE, 右值=RIGHT_VALUE)
        if _结果 >= ZERO_VALUE:
            pass
        return

    def register_handlers(self):
        # 注册事件处理器。
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

