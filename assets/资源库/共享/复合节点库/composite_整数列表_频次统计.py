"""
composite_id: composite_整数列表_频次统计
node_name: 整数列表_统计出现次数
node_description: 统计整数列表中每个整数出现的次数，输出为字典（键=整数，值=整数）
scope: server
"""

# Python 等价写法：
# - 计数字典 = collections.Counter(输入列表)
#
# 示例输入输出：
# - 输入列表=[1, 2, 1] -> 计数字典={1: 2, 2: 1}
#
# Graph Code 调用示例（server，语法糖：直接写复合节点名(...)）：
# - 计数字典: "整数_整数字典" = 整数列表_统计出现次数(输入列表=输入列表)

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
class 整数列表_统计出现次数:
    """整数列表频次统计（Counter）"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 统计(self, 输入列表: "整数列表"):
        """返回字典：键为列表元素，值为出现次数。"""
        流程入("流程入")
        数据入("输入列表", pin_type="整数列表")
        数据出("计数字典", pin_type="整数_整数字典", variable="计数字典")

        # 注意：Graph Code 的端口类型推断以“赋值上的中文类型注解”为主；
        # 仅写在函数签名上的类型注解不一定能覆盖所有推断场景，因此这里显式落盘一次。
        输入列表_入参: "整数列表" = 输入列表

        _, 待迭代列表 = 获取局部变量(self.game, 初始值=输入列表_入参)

        计数字典: "整数_整数字典" = {0: 0}
        清空字典(self.game, 字典=计数字典)

        列表长度: "整数" = 获取列表长度(self.game, 列表=待迭代列表)
        for 当前序号 in range(列表长度):
            当前元素: "整数" = 获取列表对应值(self.game, 列表=待迭代列表, 序号=当前序号)
            已存在: "布尔值" = 查询字典是否包含特定键(self.game, 字典=计数字典, 键=当前元素)
            if 已存在:
                当前计数: "整数" = 以键查询字典值(self.game, 字典=计数字典, 键=当前元素)
                新计数: "整数" = 加法运算(self.game, 左值=当前计数, 右值=1)
                对字典设置或新增键值对(self.game, 字典=计数字典, 键=当前元素, 值=新计数)
            else:
                对字典设置或新增键值对(self.game, 字典=计数字典, 键=当前元素, 值=1)

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


