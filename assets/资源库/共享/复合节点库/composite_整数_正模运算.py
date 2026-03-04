"""
composite_id: composite_整数_正模运算
node_name: 整数_正模运算
node_description: 正模运算（整数）：返回 Python 语义的 a % m（结果保证在 [0, m-1]）
scope: server
"""

# Python 等价写法：
# - 结果 = 被模数 % 模数
#
# 示例输入输出（模数为正整数时）：
# - 被模数=-2, 模数=4 -> 结果=2
# - 被模数=5,  模数=4 -> 结果=1
#
# Graph Code 示例（推荐写法：原生运算符语法糖，自动改写为共享复合节点）：
# - 结果: "整数" = 被模数 % 模数
#
# Graph Code 调用示例（server，手动实例化）：
# - self._正模整数 = 整数_正模运算(self.game, self.owner_entity)
# - 结果: "整数" = self._正模整数.计算(被模数=被模数, 模数=模数)

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

# 支持直接运行本文件（python composite_xxx.py）时的导入路径。
# 注意：只注入 workspace root；不注入 `app/` 到 sys.path（避免把 `app/ui` 变成顶层 `ui` 包）。
_workspace_root = next(directory for directory in Path(__file__).resolve().parents if (directory / "pyrightconfig.json").is_file())
_workspace_root_text = str(_workspace_root)
if _workspace_root_text not in sys.path:
    sys.path.insert(0, _workspace_root_text)

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403
from engine.nodes.composite_spec import composite_class, flow_entry

if TYPE_CHECKING:
    from engine.graph.composite.pin_api import 流程入, 流程出, 数据入, 数据出


@composite_class
class 整数_正模运算:
    """正模运算（整数）

    目的：
    - 部分运行环境中，【模运算】节点可能采用“负余数”语义（例如 -2 mod 4 == -2）；
    - 业务侧更常期望 Python 的 `%` 语义（模数为正时余数恒为非负）。

    该复合节点实现模板：((a % m) + m) % m
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 计算(self, 被模数: "整数", 模数: "整数"):
        """返回正模结果（整数）"""
        数据入("被模数", pin_type="整数")
        数据入("模数", pin_type="整数")
        数据出("结果", pin_type="整数", variable="结果")

        余数: "整数" = 模运算(self.game, 被模数=被模数, 模数=模数)
        余数修正: "整数" = 加法运算(self.game, 左值=余数, 右值=模数)
        结果: "整数" = 模运算(self.game, 被模数=余数修正, 模数=模数)
        return 结果


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


