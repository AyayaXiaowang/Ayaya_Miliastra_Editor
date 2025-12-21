"""
composite_id: composite_多分支_示例_类格式
node_name: 多分支_示例_类格式
node_description: 使用 match-case 根据整数分支输出一个分支标签字符串，由外部节点图决定如何分支
scope: server
"""

from __future__ import annotations

import sys
from pathlib import Path

# 复合节点库位于 `.../Graph_Generater/assets/资源库/复合节点库/`，
# 因此当前文件向上 3 层即为项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[3]
APP_DIR = PROJECT_ROOT / "app"
ASSETS_ROOT = PROJECT_ROOT / "assets"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))
if str(ASSETS_ROOT) not in sys.path:
    sys.path.insert(2, str(ASSETS_ROOT))

from runtime.engine.graph_prelude_server import *
from engine.nodes.composite_spec import composite_class, flow_entry
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.graph.composite.pin_api import 流程入, 流程出, 数据入, 数据出


@composite_class
class 多分支_示例_类格式:
    """多分支复合节点示例（单流程入 + 多个流程出口）

    功能：
    - 输入一个整数 `分支值`
    - 根据取值从不同的流程出口之一流出：`分支为0` / `分支为1` / `分支为其他`

    用途：
    - 外部节点图可以把不同的流程出口接到不同的后续节点，实现清晰直观的多分支流程
    - 同时用于验证类格式复合节点在多分支（match-case）场景下的多流程出口行为是否正常
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 按整数多分支(self, 分支值: "整数"):
        """根据整数分支选择流程出口"""
        # 虚拟引脚声明：1 个流程入 + 1 个数据入 + 3 个流程出口
        流程入("流程入")
        数据入("分支值", pin_type="整数")

        # 使用 match-case 选择流程出口
        match 分支值:
            case 0:
                流程出("分支为0")
            case 1:
                流程出("分支为1")
            case _:
                流程出("分支为其他")


if __name__ == "__main__":
    import pathlib
    from runtime.engine.node_graph_validator import validate_file

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


