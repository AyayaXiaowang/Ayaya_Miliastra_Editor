"""
composite_id: composite_TS_合并引脚_扇出_v1
node_name: TS_合并引脚_扇出_v1
node_description: 回归测试：单外部数据入引脚扇出到多个内部节点端口（mapped_ports 多条），用于验证 port_mappings/合并规则写回稳定性。
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
class TS_合并引脚_扇出_v1:
    """合并引脚/扇出：同一外部输入映射到多个内部端口。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 扇出_双倍与平方(self, 数值: "浮点数"):
        数据入("数值", pin_type="浮点数")
        数据出("双倍", pin_type="浮点数", variable="双倍")
        数据出("平方", pin_type="浮点数", variable="平方")

        # 同一个外部 pin「数值」同时接到多个内部端口：用于生成多条 mapped_ports/InterfaceMapping
        双倍: "浮点数" = 加法运算(self.game, 左值=数值, 右值=数值)
        平方: "浮点数" = 乘法运算(self.game, 左值=数值, 右值=数值)
        return 双倍, 平方


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

