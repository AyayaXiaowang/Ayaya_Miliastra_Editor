"""
graph_id: client_enum_coverage_scan_state_and_input_device_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_client_扫描状态与输入设备
graph_type: client
description: 枚举覆盖图（拆分版）：覆盖扫描状态与输入设备类型等输出枚举候选项；每个事件 ≤ 20 节点。
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


class 校准_枚举覆盖_v1_client_扫描状态与输入设备:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    def on_节点图开始(self):
        自身实体: "实体" = 获取自身实体(self.game)
        节点图开始(self.game)

        __扫描状态 = 获取实体扫描状态(self.game, 目标实体=自身实体)
        设置局部变量(self.game, 变量名="校准_枚举比较结果", 变量值=枚举匹配(self.game, 枚举1=__扫描状态, 枚举2="目标不可用"))
        设置局部变量(self.game, 变量名="校准_枚举比较结果", 变量值=枚举匹配(self.game, 枚举1=__扫描状态, 枚举2="当前扫描目标"))
        设置局部变量(self.game, 变量名="校准_枚举比较结果", 变量值=枚举匹配(self.game, 枚举1=__扫描状态, 枚举2="候选目标"))
        设置局部变量(self.game, 变量名="校准_枚举比较结果", 变量值=枚举匹配(self.game, 枚举1=__扫描状态, 枚举2="不满足条件"))

        __输入设备类型 = 获得玩家客户端输入设备类型(self.game)
        设置局部变量(self.game, 变量名="校准_枚举比较结果", 变量值=枚举匹配(self.game, 枚举1=__输入设备类型, 枚举2="键盘鼠标"))
        设置局部变量(self.game, 变量名="校准_枚举比较结果", 变量值=枚举匹配(self.game, 枚举1=__输入设备类型, 枚举2="手柄"))
        设置局部变量(self.game, 变量名="校准_枚举比较结果", 变量值=枚举匹配(self.game, 枚举1=__输入设备类型, 枚举2="触屏"))

        return

    def register_handlers(self):
        return


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))


