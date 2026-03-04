"""
composite_id: composite_合并引脚_示例_类格式
node_name: 合并引脚_示例_类格式
node_description: 演示“一个外部数据入引脚映射到多个内部节点输入”（合并/扇出映射），用于验证导出 .gia 的 mapped_ports/InterfaceMapping 稳定性
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
class 合并引脚_示例_类格式:
    """合并/扇出引脚示例

    目标：
    - 外部仅提供 1 个数据入：共享整数
    - 内部把该共享整数分别接到 2 个加法节点的不同输入端口（形成“一对多 mapped_ports”）
    - 输出两个计算结果，便于宿主图继续连线
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 合并整数输入(
        self,
        共享整数: "整数",
        加数A: "整数",
        加数B: "整数",
    ):
        流程入("流程入")
        数据入("共享整数", pin_type="整数")
        数据入("加数A", pin_type="整数")
        数据入("加数B", pin_type="整数")

        数据出("结果A", pin_type="整数", variable="结果A")
        数据出("结果B", pin_type="整数", variable="结果B")

        # 关键：同一个外部输入“共享整数”在内部被使用两次（映射到两个不同节点的两个输入端口）
        结果A = 加法运算(self.game, 左值=共享整数, 右值=加数A)
        结果B = 加法运算(self.game, 左值=共享整数, 右值=加数B)

        # 让子图内存在可建模的流程节点（保证虚拟流程引脚可映射到子图流程连线）
        打印字符串(self.game, 字符串="合并引脚复合节点：已计算结果")

        流程出("流程出")
        return 结果A, 结果B


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

