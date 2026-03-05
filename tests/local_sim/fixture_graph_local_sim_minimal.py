"""
graph_id: local_sim_minimal_server_01
graph_name: LocalSim_Minimal_Server
graph_type: server
description: 本地测试（Local Graph Sim）最小夹具节点图：

- 覆盖 ui_key: 占位符 → 稳定 index 的映射（用于离线模拟 UI click/patch）
- 覆盖 “布局索引_*” 的 layout_index fallback（基于描述里的 HTML 文件名）
- 覆盖 “界面控件组触发时” 事件的最小回调链路
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
        description="本地测试用：btn_allow 的稳定伪索引（ui_key 占位符）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="按钮索引_btn_exit",
        variable_type="整数",
        default_value="ui_key:HTML导入_界面布局__btn_exit__btn_item",
        description="本地测试用：btn_exit 的稳定伪索引（ui_key 占位符）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="按钮索引_btn_tut_g0",
        variable_type="整数",
        default_value="ui_key:HTML导入_界面布局__tutorial_overlay__guide_0__btn_item",
        description="本地测试用：tutorial_overlay.guide_0 的稳定伪索引（ui_key 占位符）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="布局索引_页A",
        variable_type="整数",
        default_value=0,
        description="本地测试用：UI布局索引（page_a.html）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="布局索引_页B",
        variable_type="整数",
        default_value=0,
        description="本地测试用：UI布局索引（page_b.html）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="最后一次点击GUID",
        variable_type="整数",
        default_value=0,
        description="本地测试用：记录最近一次 UI click 注入的 GUID。",
        is_exposed=False,
    ),
]


class LocalSim_Minimal_Server:
    def __init__(self, game, owner_entity):
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
        设置节点图变量(
            self.game,
            变量名="最后一次点击GUID",
            变量值=界面控件组组合索引,
            是否触发事件=False,
        )

    def register_handlers(self):
        self.game.register_event_handler(
            "界面控件组触发时",
            self.on_界面控件组触发时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

