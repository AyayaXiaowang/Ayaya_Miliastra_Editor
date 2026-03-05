"""
composite_id: composite_条件选择_整数
node_name: 三元表达式_整数
node_description: 三元表达式（整数）：X if 条件 else Y
scope: server
"""

# Python 等价写法：
# - 选择结果 = 条件为真输出 if 条件 else 条件为假输出
#
# 示例输入输出：
# - 条件=True,  条件为真输出=7, 条件为假输出=0 -> 选择结果=7
# - 条件=False, 条件为真输出=7, 条件为假输出=0 -> 选择结果=0
#
# Graph Code 示例（推荐写法：语法糖，自动改写为共享复合节点）：
# - 选择结果: "整数" = 条件为真输出 if 条件 else 条件为假输出
#
# Graph Code 调用示例（server，手动实例化）：
# - self._三元整数 = 三元表达式_整数(self.game, self.owner_entity)
# - 选择结果: "整数" = self._三元整数.按条件选择(条件=条件, 条件为真输出=条件为真输出, 条件为假输出=条件为假输出)

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
class 三元表达式_整数:
    """三元表达式（整数）

    用途：
    - Graph Code 禁止使用三元表达式 `A if 条件 else B`；
    - 该复合节点提供等价的“按条件选择整数”的单节点替代方案，便于在节点编辑器中复用。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 按条件选择(self, 条件: "布尔值", 条件为真输出: "整数", 条件为假输出: "整数"):
        """根据条件选择输出（整数）"""
        流程入("流程入")
        数据入("条件", pin_type="布尔值")
        数据入("条件为真输出", pin_type="整数")
        数据入("条件为假输出", pin_type="整数")
        数据出("选择结果", pin_type="整数", variable="选择结果")
        流程出("完成")

        选择结果句柄, 选择结果 = 获取局部变量(self.game, 初始值=条件为真输出)
        if 条件:
            设置局部变量(self.game, 局部变量=选择结果句柄, 值=条件为真输出)
        else:
            设置局部变量(self.game, 局部变量=选择结果句柄, 值=条件为假输出)

        return 选择结果


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


