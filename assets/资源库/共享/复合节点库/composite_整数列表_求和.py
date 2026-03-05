"""
composite_id: composite_整数列表_求和
node_name: 整数列表_求和
node_description: 计算整数列表的元素总和（替代不受支持的 sum(列表)）
scope: server
"""

# Python 等价写法：
# - 总和 = sum(输入列表)
#
# 示例输入输出：
# - 输入列表=[1, 2, 3] -> 总和=6
#
# Graph Code 示例（推荐写法：语法糖，自动改写为共享复合节点）：
# - 总和: "整数" = sum(输入列表)
#
# Graph Code 调用示例（server，手动实例化）：
# - self._整数求和 = 整数列表_求和(self.game, self.owner_entity)
# - 总和: "整数" = self._整数求和.计算(输入列表=输入列表)

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
class 整数列表_求和:
    """整数列表求和"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 计算(self, 输入列表: "整数列表"):
        """返回输入列表所有元素的总和；空列表返回 0。"""
        流程入("流程入")
        数据入("输入列表", pin_type="整数列表")
        数据出("总和", pin_type="整数", variable="总和")
        流程出("完成")

        # 注意：Graph Code 的端口类型推断以“赋值上的中文类型注解”为主；
        # 仅写在函数签名上的类型注解不一定能覆盖所有推断场景，因此这里显式落盘一次。
        输入列表_入参: "整数列表" = 输入列表

        _, 输入列表值 = 获取局部变量(self.game, 初始值=输入列表_入参)

        初始总和: "整数" = 0 + 0
        总和句柄, 总和 = 获取局部变量(self.game, 初始值=初始总和)

        列表长度: "整数" = 获取列表长度(self.game, 列表=输入列表值)
        for 当前序号 in range(列表长度):
            当前元素: "整数" = 获取列表对应值(self.game, 列表=输入列表值, 序号=当前序号)
            新总和: "整数" = 加法运算(self.game, 左值=总和, 右值=当前元素)
            设置局部变量(self.game, 局部变量=总和句柄, 值=新总和)
            总和 = 新总和

        return 总和


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


