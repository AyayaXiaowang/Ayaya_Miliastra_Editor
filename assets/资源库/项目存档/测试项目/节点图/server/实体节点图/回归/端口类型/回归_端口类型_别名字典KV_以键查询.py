"""
graph_id: server_regression_port_type_typed_dict_alias_query_by_key
graph_name: 回归_端口类型_别名字典KV_以键查询
graph_type: server
description: |
  最小回归样本：覆盖 “别名字典端口(K/V) 约束 + 查询节点泛型实例化” 的端口类型口径。

  目的：
  - 校验层：typed dict alias（例如 `字符串-整数字典`）应能驱动 `以键查询字典值` 的输出类型收敛为 `整数`。
  - 工具链：作为 `validate-graphs --all` 的回归样本，确保端口类型快照/有效类型推断链路不回退为泛型。
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


class 回归_端口类型_别名字典KV_以键查询:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        字典: "字符串-整数字典" = {"a": 1}
        值: "整数" = 以键查询字典值(self.game, 字典=字典, 键="a")
        _和: "整数" = 加法运算(self.game, 左值=值, 右值=1)
        if _和 > 0:
            pass
        return

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

