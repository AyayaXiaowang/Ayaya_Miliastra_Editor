"""
composite_id: composite_单数据引脚_示例_类格式
node_name: 单数据引脚_示例_类格式
node_description: 演示“只有一个数据入/数据出”的最小复合节点，用于验证导出 .gia 的最小 pin 集合与映射稳定性
scope: server
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

# 支持直接运行本文件（python composite_xxx.py）时的导入路径。
# 注意：只注入 workspace root；不注入 `app/` 到 sys.path（避免把 `app/ui` 变成顶层 `ui` 包）。
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


@composite_class
class 单数据引脚_示例_类格式:
    """单数据引脚最小示例（flow + 1 data in/out）"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 回声(self, 输入字符串: "字符串"):
        流程入("流程入")
        数据入("输入字符串", pin_type="字符串")
        数据出("回声", pin_type="字符串", variable="回声")

        _句柄, 回声 = 获取局部变量(self.game, 初始值=输入字符串)
        打印字符串(self.game, 字符串="单数据引脚复合节点：已生成回声")
        流程出("流程出")
        return 回声


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
            for 序号, 错误文本 in enumerate(警告列表, start=1):
                print(f"  [{序号}] {错误文本}")
    print("=" * 80)
    if not 是否通过:
        sys.exit(1)

