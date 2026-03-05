"""
graph_id: server_regression_port_type_event_mapping_entity_created
graph_name: 回归_端口类型_event映射_实体创建时
graph_type: server
description: |
  最小回归样本：覆盖 `node_def_ref.kind="event"` 的 NodeDef 定位口径（category/title -> builtin_key）。

  目的：
  - `scan-event-migration`：应将事件节点标记为 mappable（映射到 builtin key）。
  - `validate-graphs --all`：测试项目中的回归样本应被收集并通过。
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


class 回归_端口类型_event映射_实体创建时:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 最小节点调用：确保校验入口会走到 node library / 端口规则。
        _结果: "整数" = 加法运算(self.game, 左值=1, 右值=2)
        if _结果 >= 0:
            pass
        return

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

