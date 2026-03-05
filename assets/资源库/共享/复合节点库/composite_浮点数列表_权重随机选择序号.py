"""
composite_id: composite_浮点数列表_权重随机选择序号
node_name: 权重列表_随机选序号
node_description: 按权重随机选择一个序号（权重为浮点数列表）
scope: server
"""

# Python 等价写法：
# - 选中序号 = random.choices(range(len(权重列表)), weights=权重列表, k=1)[0]
# - 空列表：返回 选中序号=-1，是否成功=False
#
# 示例输入输出（一次随机结果示例）：
# - 权重列表=[0.1, 0.3, 0.6] -> 是否成功=True, 选中序号=0/1/2（按权重概率）
# - 权重列表=[] -> 是否成功=False, 选中序号=-1
#
# Graph Code 调用示例（server，语法糖：直接写复合节点名(...)；多数据出用“元组赋值”承接）：
# - 是否成功, 选中序号 = 权重列表_随机选序号(权重列表=权重列表)

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
class 权重列表_随机选序号:
    """浮点数权重列表 → 随机序号"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 选择(self, 权重列表: "浮点数列表"):
        """按权重随机选一个序号。"""
        流程入("流程入")
        数据入("权重列表", pin_type="浮点数列表")
        数据出("是否成功", pin_type="布尔值", variable="是否成功")
        数据出("选中序号", pin_type="整数", variable="选中序号")

        是否成功句柄, 是否成功 = 获取局部变量(self.game, 初始值=False)
        选中序号句柄, 选中序号 = 获取局部变量(self.game, 初始值=-1)

        权重列表句柄, 权重列表值 = 获取局部变量(self.game, 初始值=权重列表)
        列表长度: "整数" = 获取列表长度(self.game, 列表=权重列表值)
        列表非空: "布尔值" = 数值大于(self.game, 左值=列表长度, 右值=0)

        if 列表非空:
            设置局部变量(self.game, 局部变量=是否成功句柄, 值=True)

            总权重: "浮点数" = 0.0 + 0.0
            for 当前权重 in 权重列表值:
                总权重 += 当前权重

            随机值: "浮点数" = 获取随机浮点数(self.game, 下限=0.0, 上限=总权重)

            累计权重: "浮点数" = 0.0 + 0.0
            当前序号: "整数" = 0 + 0
            是否已选中句柄, 是否已选中 = 获取局部变量(self.game, 初始值=False)

            for 当前权重 in 权重列表值:
                累计权重 += 当前权重
                随机值小于累计: "布尔值" = 数值小于(self.game, 左值=随机值, 右值=累计权重)
                if 随机值小于累计:
                    设置局部变量(self.game, 局部变量=选中序号句柄, 值=当前序号)
                    设置局部变量(self.game, 局部变量=是否已选中句柄, 值=True)
                    break
                当前序号 += 1

            if not 是否已选中:
                最后序号: "整数" = 减法运算(self.game, 左值=列表长度, 右值=1)
                设置局部变量(self.game, 局部变量=选中序号句柄, 值=最后序号)

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


