"""
composite_id: composite_整数列表_按整数键分组
node_name: 整数列表_按键分组
node_description: 按“分组键列表”对“输入列表”分组，输出字典（键=整数，值=整数列表）
scope: server
"""

# Python 等价写法：
# - 分组字典: dict[int, list[int]] = {}
# - for 值, 键 in zip(输入列表, 分组键列表):
#       分组字典.setdefault(键, []).append(值)
#
# 示例输入输出：
# - 输入列表=[10, 11, 20], 分组键列表=[1, 1, 2] -> 分组字典={1: [10, 11], 2: [20]}
#
# Graph Code 调用示例（server，语法糖：直接写复合节点名(...)）：
# - 分组字典: "整数_整数列表字典" = 整数列表_按键分组(输入列表=输入列表, 分组键列表=分组键列表)

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
class 整数列表_按键分组:
    """整数列表按整数键分组"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 分组(self, 输入列表: "整数列表", 分组键列表: "整数列表"):
        """返回字典：键为分组键，值为对应的整数列表（按输入顺序追加）。"""
        流程入("流程入")
        数据入("输入列表", pin_type="整数列表")
        数据入("分组键列表", pin_type="整数列表")
        数据出("分组字典", pin_type="整数_整数列表字典", variable="分组字典")

        # 注意：Graph Code 的端口类型推断以“赋值上的中文类型注解”为主；
        # 仅写在函数签名上的类型注解不一定能覆盖所有推断场景，因此这里显式落盘一次。
        输入列表_入参: "整数列表" = 输入列表
        分组键列表_入参: "整数列表" = 分组键列表

        _, 输入列表值 = 获取局部变量(self.game, 初始值=输入列表_入参)
        _, 分组键列表值 = 获取局部变量(self.game, 初始值=分组键列表_入参)

        输入长度: "整数" = 获取列表长度(self.game, 列表=输入列表值)
        键长度: "整数" = 获取列表长度(self.game, 列表=分组键列表值)

        有效长度句柄, 有效长度 = 获取局部变量(self.game, 初始值=键长度)
        输入更短: "布尔值" = 数值小于(self.game, 左值=输入长度, 右值=键长度)
        if 输入更短:
            设置局部变量(self.game, 局部变量=有效长度句柄, 值=输入长度)

        占位列表: "整数列表" = [0]
        分组字典: "整数_整数列表字典" = {0: 占位列表}
        清空字典(self.game, 字典=分组字典)

        for 当前序号 in range(有效长度):
            当前值: "整数" = 获取列表对应值(self.game, 列表=输入列表值, 序号=当前序号)
            当前键: "整数" = 获取列表对应值(self.game, 列表=分组键列表值, 序号=当前序号)

            已存在: "布尔值" = 查询字典是否包含特定键(self.game, 字典=分组字典, 键=当前键)
            if 已存在:
                当前分组列表: "整数列表" = 以键查询字典值(self.game, 字典=分组字典, 键=当前键)
                对列表插入值(self.game, 列表=当前分组列表, 插入序号=999999, 插入值=当前值)
                对字典设置或新增键值对(self.game, 字典=分组字典, 键=当前键, 值=当前分组列表)
            else:
                新分组列表: "整数列表" = [0]
                清除列表(self.game, 列表=新分组列表)
                对列表插入值(self.game, 列表=新分组列表, 插入序号=999999, 插入值=当前值)
                对字典设置或新增键值对(self.game, 字典=分组字典, 键=当前键, 值=新分组列表)

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


