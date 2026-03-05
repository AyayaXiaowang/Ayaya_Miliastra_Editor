"""
composite_id: composite_实体列表_查找首次出现序号
node_name: 实体列表_查找首次出现序号
node_description: 返回目标实体在实体列表中首次出现的序号（未找到返回-1），并输出是否找到
scope: server
"""

# Python 等价写法：
# - 序号 = 输入列表.index(目标实体)  # 未找到会抛异常；本复合节点改为返回 -1
# - 是否找到 = (序号 != -1)
#
# 示例输入输出：
# - 输入列表=[实体A, 实体B], 目标实体=实体B -> 是否找到=True, 首次出现序号=1
# - 输入列表=[实体A, 实体B], 目标实体=实体C -> 是否找到=False, 首次出现序号=-1
#
# Graph Code 调用示例（server，语法糖：直接写复合节点名(...)；多数据出用“元组赋值”承接）：
# - 是否找到, 首次出现序号 = 实体列表_查找首次出现序号(输入列表=输入列表, 目标实体=目标实体)

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
class 实体列表_查找首次出现序号:
    """实体列表 index（首次出现序号）"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 查找(self, 输入列表: "实体列表", 目标实体: "实体"):
        """未找到返回 -1；是否找到 为 False。"""
        流程入("流程入")
        数据入("输入列表", pin_type="实体列表")
        数据入("目标实体", pin_type="实体")
        数据出("是否找到", pin_type="布尔值", variable="是否找到")
        数据出("首次出现序号", pin_type="整数", variable="首次出现序号")

        是否找到句柄, 是否找到 = 获取局部变量(self.game, 初始值=False)
        首次出现序号句柄, 首次出现序号 = 获取局部变量(self.game, 初始值=-1)
        待迭代列表句柄, 待迭代列表 = 获取局部变量(self.game, 初始值=输入列表)

        当前序号: "整数" = 0 + 0
        for 当前实体 in 待迭代列表:
            是否命中: "布尔值" = 是否相等(self.game, 输入1=当前实体, 输入2=目标实体)
            if 是否命中:
                设置局部变量(self.game, 局部变量=是否找到句柄, 值=True)
                设置局部变量(self.game, 局部变量=首次出现序号句柄, 值=当前序号)
                break
            当前序号 += 1

        流程出("完成")


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


