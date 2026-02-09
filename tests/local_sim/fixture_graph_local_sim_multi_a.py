"""
graph_id: local_sim_multi_graph_a
graph_name: LocalSim_Multi_A
graph_type: server
description: 本地测试（Local Graph Sim）多图挂载夹具：主图

- 监听 UI click 事件（界面控件组触发时）。
- 写入 owner 自定义变量，用于验证“多节点图同时挂载 + 同一事件多回调”。
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


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="按钮索引_btn_allow",
        variable_type="整数",
        default_value="ui_key:HTML导入_界面布局__btn_allow__btn_item",
        description="本地测试：用于触发 click 注入。",
        is_exposed=False,
    ),
]

VAR_MAIN_CLICKED: "字符串" = "main_clicked"


class LocalSim_Multi_A:
    def __init__(self, game: GameRuntime, owner_entity: "实体"):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_界面控件组触发时(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        界面控件组组合索引: "整数",
        界面控件组索引: "整数",
    ) -> None:
        设置自定义变量(
            self.game,
            目标实体=self.owner_entity,
            变量名=VAR_MAIN_CLICKED,
            变量值=True,
            是否触发事件=False,
        )
        return

    def register_handlers(self):
        self.game.register_event_handler(
            "界面控件组触发时",
            self.on_界面控件组触发时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

