"""
graph_id: server_ts_suite_01_all_types
graph_name: TS_测试集_01_全类型_复合调用
graph_type: server
description: 回归测试：宿主图调用“TS_全类型写入_v1”，覆盖写回侧支持的主要 VarType（标量/列表/typed dict alias/向量/ID/阵营/结构体占位）。
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

from 资源库.项目存档.测试项目.复合节点库.composite_TS_全类型写入_v1 import TS_全类型写入_v1
from 资源库.项目存档.测试项目.复合节点库.composite_TS_列表字典写入_v1 import TS_列表字典写入_v1


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="TS_标记_已执行",
        variable_type="布尔值",
        default_value=False,
        description="用于确认宿主图已触发并调用复合节点。",
        is_exposed=False,
    ),
]


class TS_测试集_01_全类型_复合调用:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.TS_全类型写入_v1 = TS_全类型写入_v1(game, owner_entity)
        self.TS_列表字典写入_v1 = TS_列表字典写入_v1(game, owner_entity)

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        self.TS_全类型写入_v1.写入_标量与ID(
            整数值=123,
            浮点值=3.25,
            布尔值=True,
            文本="TS_文本_01",
            输入GUID=事件源GUID,
            输入实体=事件源实体,
            输入阵营=0,
            输入配置ID=1,
            输入元件ID=1,
            输入向量=(1.0, 2.0, 3.0),
        )

        映射_字符串到整数: "字符串-整数字典" = {"a": 1, "b": 2}
        占位_配置ID_1: "配置ID" = 1
        占位_配置ID_2: "配置ID" = 2
        占位_元件ID_1: "元件ID" = 1
        占位_阵营_0: "阵营" = 0
        self.TS_列表字典写入_v1.写入_列表与字典(
            整数列表=[1, 2, 3],
            字符串列表=["a", "b"],
            GUID列表=[事件源GUID],
            布尔列表=[True, False],
            浮点列表=[0.5, 1.5],
            向量列表=[(0.0, 1.0, 2.0)],
            配置ID列表=[占位_配置ID_1, 占位_配置ID_2],
            元件ID列表=[占位_元件ID_1],
            阵营列表=[占位_阵营_0],
            字典_字符串到整数=映射_字符串到整数,
        )

        设置节点图变量(
            self.game,
            变量名="TS_标记_已执行",
            变量值=True,
            是否触发事件=False,
        )

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

