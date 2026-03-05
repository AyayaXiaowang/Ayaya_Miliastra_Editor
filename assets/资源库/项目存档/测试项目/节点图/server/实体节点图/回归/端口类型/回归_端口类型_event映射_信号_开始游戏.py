"""
graph_id: server_test_project_regression_port_type_event_mapping_start_game_signal
graph_name: 回归_端口类型_event映射_信号_开始游戏
graph_type: server
description: |
  最小回归样本（测试项目）：覆盖 `node_def_ref.kind="event"` 的 NodeDef 定位口径（category/title -> builtin_key）。

  触发方式：
  - 监听信号 `开始游戏`（定义位于 `assets/资源库/项目存档/测试项目/管理配置/信号/signal_start_game.py`）。

  预期：
  - `validate-graphs` 校验通过（不允许出现“纯数据孤立链路”的 warning）。
  - `scan-event-migration` 在 active_package_id=测试项目 的作用域下应能将该 event 节点标记为 mappable。
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


class 回归_端口类型_event映射_信号_开始游戏:
    def __init__(self, game: GameRuntime, owner_entity: "实体"):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_开始游戏(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        关卡序号: "整数",
    ) -> None:
        # 最小节点链路：用 if 消费查询/运算输出，避免产生“纯数据孤立链路”告警。
        _关卡序号: "整数" = 加法运算(self.game, 左值=关卡序号, 右值=0)
        if _关卡序号 >= 0:
            pass
        return

    def register_handlers(self):
        self.game.register_event_handler("开始游戏", self.on_开始游戏, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

