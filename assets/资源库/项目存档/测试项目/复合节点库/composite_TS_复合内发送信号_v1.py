"""
composite_id: composite_TS_复合内发送信号_v1
node_name: TS_复合内发送信号_v1
node_description: 回归测试：复合节点子图内发送信号（多参数、多类型），用于验证写回侧信号节点与复合递归的落盘。
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
    from engine.graph.composite.pin_api import 流程入, 流程出, 数据入, 数据出


_TS_SIGNAL_NAME: str = "TS_Signal_AllTypes_001"


@composite_class
class TS_复合内发送信号_v1:
    """复合内发送信号（用于进游戏验收）。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 触发_全类型信号(
        self,
        数字A: "整数",
        数字B: "浮点数",
        文本: "字符串",
        是否启用: "布尔值",
        关联GUID: "GUID",
    ):
        流程入("流程入")
        数据入("数字A", pin_type="整数")
        数据入("数字B", pin_type="浮点数")
        数据入("文本", pin_type="字符串")
        数据入("是否启用", pin_type="布尔值")
        数据入("关联GUID", pin_type="GUID")

        # 关键覆盖：复合节点子图内出现 Send_Signal，并携带多参数（多 VarType）
        发送信号(
            self.game,
            信号名=_TS_SIGNAL_NAME,
            数字A=数字A,
            数字B=数字B,
            文本=文本,
            是否启用=是否启用,
            关联GUID=关联GUID,
        )

        流程出("流程出")


if __name__ == "__main__":
    import pathlib

    from app.runtime.engine.node_graph_validator import validate_file

    自身文件路径 = pathlib.Path(__file__).resolve()
    是否通过, 错误列表, 警告列表 = validate_file(自身文件路径)
    print("=" * 80)
    print(f"复合节点自检: {自身文件路径.name}")
    print(f"文件: {自身文件路径}")
    if 是否通过:
        print("结果: 通过")
    else:
        print(f"结果: 未通过（错误: {len(错误列表)}，警告: {len(警告列表)}）")
        if 错误列表:
            print("\n错误明细:")
            for 序号, 错误文本 in enumerate(错误列表, start=1):
                print(f"  [{序号}] {错误文本}")
        if 警告列表:
            print("\n警告明细:")
            for 序号, 警告文本 in enumerate(警告列表, start=1):
                print(f"  [{序号}] {警告文本}")
    print("=" * 80)
    if not 是否通过:
        sys.exit(1)

