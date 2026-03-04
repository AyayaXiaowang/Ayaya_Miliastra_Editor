"""
composite_id: composite_实体列表_过滤_按布尔值列表
node_name: 实体列表_按布尔掩码过滤
node_description: 根据布尔掩码（布尔值列表）过滤实体列表（等价于 zip + if 过滤）
scope: server
"""

# Python 等价写法：
# - 结果列表 = [实体 for 实体, 保留 in zip(输入列表, 保留条件列表) if 保留]
#
# 示例输入输出：
# - 输入列表=[实体A, 实体B, 实体C], 保留条件列表=[True, False, True] -> 结果列表=[实体A, 实体C]
#
# Graph Code 调用示例（server，语法糖：直接写复合节点名(...)）：
# - 结果列表: "实体列表" = 实体列表_按布尔掩码过滤(输入列表=输入列表, 保留条件列表=保留条件列表)

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
class 实体列表_按布尔掩码过滤:
    """实体列表过滤（按布尔掩码）"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 过滤(self, 输入列表: "实体列表", 保留条件列表: "布尔值列表"):
        """返回过滤后的实体列表；长度按 zip 规则裁剪为两列表较短者。"""
        流程入("流程入")
        数据入("输入列表", pin_type="实体列表")
        数据入("保留条件列表", pin_type="布尔值列表")
        数据出("结果列表", pin_type="实体列表", variable="结果列表")
        流程出("完成")

        # 注意：Graph Code 的端口类型推断以“赋值上的中文类型注解”为主；
        # 仅写在函数签名上的类型注解不一定能覆盖所有推断场景，因此这里显式落盘一次。
        输入列表_入参: "实体列表" = 输入列表
        保留条件列表_入参: "布尔值列表" = 保留条件列表

        _, 输入列表值 = 获取局部变量(self.game, 初始值=输入列表_入参)
        _, 条件列表值 = 获取局部变量(self.game, 初始值=保留条件列表_入参)

        输入长度: "整数" = 获取列表长度(self.game, 列表=输入列表值)
        条件长度: "整数" = 获取列表长度(self.game, 列表=条件列表值)

        有效长度句柄, 有效长度 = 获取局部变量(self.game, 初始值=条件长度)
        输入更短: "布尔值" = 数值小于(self.game, 左值=输入长度, 右值=条件长度)
        if 输入更短:
            设置局部变量(self.game, 局部变量=有效长度句柄, 值=输入长度)

        结果列表: "实体列表" = [self.owner_entity]
        清除列表(self.game, 列表=结果列表)

        for 当前序号 in range(有效长度):
            当前条件: "布尔值" = 获取列表对应值(self.game, 列表=条件列表值, 序号=当前序号)
            if 当前条件:
                当前实体: "实体" = 获取列表对应值(self.game, 列表=输入列表值, 序号=当前序号)
                对列表插入值(self.game, 列表=结果列表, 插入序号=999999, 插入值=当前实体)

        return 结果列表


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


