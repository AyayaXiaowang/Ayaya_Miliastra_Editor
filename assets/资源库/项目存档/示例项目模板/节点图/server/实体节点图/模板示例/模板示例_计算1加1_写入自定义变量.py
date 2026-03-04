"""
graph_id: server_template_add_one_plus_one_write_custom_variable
graph_name: 模板示例_计算1加1_写入自定义变量
graph_type: server
description: 示例节点图（最小可复制模板）：在【实体创建时】计算 1+1 得到整数结果，并把结果写入挂载实体的指定自定义变量（变量名/是否触发事件由节点图变量控制）。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir()))
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / 'assets'))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="输出自定义变量名",
        variable_type="字符串",
        default_value="示例_一加一结果",
        description="将 1+1 的结果写入该名称对应的自定义变量（目标为挂载实体）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="是否触发自定义变量事件",
        variable_type="布尔值",
        default_value=False,
        description="是否在写入自定义变量时触发对应事件（示例默认关闭）。",
        is_exposed=False,
    ),
]

class 模板示例_计算1加1_写入自定义变量:
    """演示“计算并写入自定义变量”的最小流程：

    1. 在【实体创建时】中直接调用【加法运算】得到结果 2；
    2. 读取节点图变量中的“输出自定义变量名/是否触发自定义变量事件”作为参数；
    3. 调用【设置自定义变量】把结果写到挂载实体上，方便在编辑器中查看。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        输出变量名: "字符串" = 获取节点图变量(self.game, 变量名="输出自定义变量名")
        是否触发事件: "布尔值" = 获取节点图变量(self.game, 变量名="是否触发自定义变量事件")

        计算结果: "整数" = 1 + 1

        设置自定义变量(
            self.game,
            目标实体=self.owner_entity,
            变量名=输出变量名,
            变量值=计算结果,
            是否触发事件=是否触发事件,
        )

    # ---------------------------- 注册事件处理器 ----------------------------
    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )

if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))
