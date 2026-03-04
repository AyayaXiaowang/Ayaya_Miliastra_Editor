"""
composite_id: composite_冷却_检查并更新时间戳
node_name: 冷却_检查并更新时间戳
node_description: 判断是否达到冷却（当前时间戳-上次触发时间戳>=冷却秒数），并在就绪时输出更新后的上次触发时间戳
scope: server
"""

# Python 等价写法：
# - 经过秒数 = 当前时间戳 - 上次触发时间戳
# - 是否就绪 = 经过秒数 >= 冷却秒数
# - 更新后上次触发时间戳 = 当前时间戳 if 是否就绪 else 上次触发时间戳
#
# 示例输入输出：
# - 当前时间戳=100, 上次触发时间戳=90, 冷却秒数=5  -> 是否就绪=True,  更新后上次触发时间戳=100
# - 当前时间戳=100, 上次触发时间戳=98, 冷却秒数=5  -> 是否就绪=False, 更新后上次触发时间戳=98
#
# Graph Code 调用示例（server，语法糖：直接写复合节点名(...)；多数据出用“元组赋值”承接）：
# - 是否就绪, 更新后上次触发时间戳 = 冷却_检查并更新时间戳(当前时间戳=当前时间戳, 上次触发时间戳=上次触发时间戳, 冷却秒数=冷却秒数)

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
class 冷却_检查并更新时间戳:
    """冷却检测：就绪判断 + 更新时间戳"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 检查(self, 当前时间戳: "整数", 上次触发时间戳: "整数", 冷却秒数: "整数"):
        """返回是否就绪，并输出更新后的上次触发时间戳（就绪时=当前时间戳，否则保持不变）。"""
        流程入("流程入")
        数据入("当前时间戳", pin_type="整数")
        数据入("上次触发时间戳", pin_type="整数")
        数据入("冷却秒数", pin_type="整数")
        数据出("是否就绪", pin_type="布尔值", variable="是否就绪")
        数据出("更新后上次触发时间戳", pin_type="整数", variable="更新后上次触发时间戳")

        经过秒数: "整数" = 减法运算(self.game, 左值=当前时间戳, 右值=上次触发时间戳)
        是否就绪: "布尔值" = 数值大于等于(self.game, 左值=经过秒数, 右值=冷却秒数)

        更新句柄, 更新后上次触发时间戳 = 获取局部变量(self.game, 初始值=上次触发时间戳)
        if 是否就绪:
            设置局部变量(self.game, 局部变量=更新句柄, 值=当前时间戳)

        流程出("完成")
        return 是否就绪, 更新后上次触发时间戳


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


