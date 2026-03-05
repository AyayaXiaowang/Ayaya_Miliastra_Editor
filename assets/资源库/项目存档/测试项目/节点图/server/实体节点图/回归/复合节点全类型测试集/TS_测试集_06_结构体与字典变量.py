"""
graph_id: server_ts_suite_06_struct_and_typed_dict_vars
graph_name: TS_测试集_06_结构体与字典变量
graph_type: server
description: 回归测试：覆盖“结构体/结构体列表/自定义变量快照/typed dict alias”等类型在 GraphVariable（节点图变量）层的落盘与写回。
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
        name="TS_td_字符串整数字典",
        variable_type="字符串-整数字典",
        default_value={"a": 1, "b": 2},
        description="typed dict alias：用于验证写回侧能从 variable_type 推断字典 K/V 并编码 type_info。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="TS_struct_empty",
        variable_type="结构体",
        default_value=None,
        description="结构体（空值）：用于验证 empty VarBase 结构体写回。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="TS_struct_list_empty",
        variable_type="结构体列表",
        default_value=[],
        description="结构体列表（空列表）：用于验证 empty list VarBase 写回。",
        is_exposed=False,
    ),
]


class TS_测试集_06_结构体与字典变量:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 只做一次读写，确保变量节点在 GraphModel 中落盘（便于写回侧编码）。
        v: "字符串-整数字典" = 获取节点图变量(self.game, 变量名="TS_td_字符串整数字典")
        设置节点图变量(self.game, 变量名="TS_td_字符串整数字典", 变量值=v, 是否触发事件=False)

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

