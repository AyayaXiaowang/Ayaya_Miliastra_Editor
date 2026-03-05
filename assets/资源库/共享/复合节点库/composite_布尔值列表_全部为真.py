"""
composite_id: composite_布尔值列表_全部为真
node_name: 布尔值列表_全部为真
node_description: 判断布尔值列表中是否全部为真（替代 all(列表)）
scope: server
"""

# Python 等价写法：
# - 结果 = all(输入列表)
#
# 示例输入输出：
# - 输入列表=[True, True] -> 结果=True
# - 输入列表=[True, False] -> 结果=False
#
# Graph Code 示例（推荐写法：语法糖，自动改写为共享复合节点）：
# - 结果: "布尔值" = all(输入列表)
#
# Graph Code 调用示例（server，手动实例化）：
# - self._布尔全部为真 = 布尔值列表_全部为真(self.game, self.owner_entity)
# - 结果: "布尔值" = self._布尔全部为真.计算(输入列表=输入列表)

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

from app.runtime.engine.graph_prelude_server import *
from engine.nodes.composite_spec import composite_class, flow_entry

if TYPE_CHECKING:
    from engine.graph.composite.pin_api import 流程入, 流程出, 数据入, 数据出


@composite_class
class 布尔值列表_全部为真:
    """布尔值列表 all（全部为真）"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 计算(self, 输入列表: "布尔值列表"):
        """判断输入列表中是否全部为真；空列表返回 True。"""
        数据入("输入列表", pin_type="布尔值列表")
        数据出("结果", pin_type="布尔值", variable="结果")

        是否包含假: "布尔值" = 列表是否包含该值(self.game, 列表=输入列表, 值=False)
        结果: "布尔值" = not 是否包含假
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


