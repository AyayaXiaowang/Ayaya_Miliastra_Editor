"""
composite_id: composite_TS_最小布尔复合_v1
node_name: TS_最小布尔复合_v1
node_description: 最小复现：复合节点仅包含 1 个布尔虚拟引脚，并在复合子图内通过“获取局部变量”走一遍布尔类型载体 pin 落盘链路。
scope: server
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

_workspace_root = next(
    directory for directory in Path(__file__).resolve().parents if (directory / "pyrightconfig.json").is_file()
)
_workspace_root_text = str(_workspace_root)
if _workspace_root_text not in sys.path:
    sys.path.insert(0, _workspace_root_text)

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403
from engine.nodes.composite_spec import composite_class, flow_entry

if TYPE_CHECKING:
    from engine.graph.composite.pin_api import 数据入, 数据出


@composite_class
class TS_最小布尔复合_v1:
    """最小复现：布尔虚拟引脚 + 复合子图内局部变量。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 触发布尔链路(self, 布尔值: "布尔值") -> "布尔值":
        数据入("布尔值", pin_type="布尔值")

        # 复合节点校验口径：数据出不允许直接透传数据入（必须经由节点调用产生）。
        _h, 布尔回声 = 获取局部变量(self.game, 初始值=布尔值)

        数据出("布尔回声", pin_type="布尔值", variable="布尔回声")
        return 布尔回声


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

