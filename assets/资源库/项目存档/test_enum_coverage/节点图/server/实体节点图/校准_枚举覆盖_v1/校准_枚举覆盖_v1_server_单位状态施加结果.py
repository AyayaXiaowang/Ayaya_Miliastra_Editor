"""
graph_id: server_enum_coverage_add_status_result_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_server_单位状态施加结果
graph_type: server
description: 枚举覆盖图（拆分版）：执行节点【添加单位状态】的“施加结果”输出枚举候选项覆盖；每个事件 ≤ 20 节点。
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

GRAPH_VARIABLES: list[GraphVariableConfig] = []


class 校准_枚举覆盖_v1_server_单位状态施加结果:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        占位_配置ID: "配置ID" = 1000000001
        占位_字符串_浮点数字典: "字符串-浮点数字典" = {"校准_k": 1.0}

        __handle, __value = 获取局部变量(self.game, 初始值=False)
        设置局部变量(self.game, 局部变量=__handle, 值=__value)

        __施加结果, __槽位序号 = 添加单位状态(
            self.game,
            施加者实体=事件源实体,
            施加目标实体=事件源实体,
            单位状态配置ID=占位_配置ID,
            施加层数=1,
            单位状态参数字典=占位_字符串_浮点数字典,
        )

        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=__施加结果, 枚举2="失败，其它异常"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=__施加结果, 枚举2="失败，让位于其它状态"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=__施加结果, 枚举2="失败，超出并存上限"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=__施加结果, 枚举2="失败，附加叠层未成功"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=__施加结果, 枚举2="成功，施加新状态"))
        设置局部变量(self.game, 局部变量=__handle, 值=枚举是否相等(self.game, 枚举1=__施加结果, 枚举2="成功，槽位叠层"))

        return

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))


