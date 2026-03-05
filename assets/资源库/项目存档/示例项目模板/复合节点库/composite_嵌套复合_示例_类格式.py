"""
composite_id: composite_嵌套复合_示例_类格式
node_name: 嵌套复合_示例_类格式
node_description: 演示“复合节点套复合节点”：外层复合节点内部调用多分支示例与多引脚模板，并将其流程/数据组合后对外输出
scope: server
"""

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

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403
from engine.nodes.composite_spec import composite_class, flow_entry

from 资源库.项目存档.示例项目模板.复合节点库.composite_多分支_示例_类格式 import 多分支_示例_类格式
from 资源库.项目存档.示例项目模板.复合节点库.composite_多引脚模板_示例 import 多引脚模板_示例

if TYPE_CHECKING:
    from engine.graph.composite.pin_api import 流程入, 流程出, 数据入, 数据出


@composite_class
class 嵌套复合_示例_类格式:
    """嵌套复合节点示例

    设计目的：
    - 覆盖“复合节点内部调用另一个复合节点”的解析与导出路径；
    - 外层对外暴露多流程出口与多数据输出，内部复用：
      - `多分支_示例_类格式.按整数多分支`
      - `多引脚模板_示例.主流程分支`
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        # 内层复合节点实例：属性名包含类名，便于解析器稳定识别
        self.多分支_示例_类格式 = 多分支_示例_类格式(game, owner_entity)
        self.多引脚模板_示例 = 多引脚模板_示例(game, owner_entity)

    @flow_entry()
    def 组合执行并分支(
        self,
        分支值: "整数",
        输入数值A: "浮点数",
        输入数值B: "浮点数",
        说明文本: "字符串",
    ):
        流程入("流程入")
        数据入("分支值", pin_type="整数")
        数据入("输入数值A", pin_type="浮点数")
        数据入("输入数值B", pin_type="浮点数")
        数据入("说明文本", pin_type="字符串")
        数据出("求和结果", pin_type="浮点数", variable="求和结果")
        数据出("描述回声", pin_type="字符串", variable="描述回声")

        # 先执行一次“多引脚模板”的主流程，产生数据输出，并在内部形成一个二分支流程
        match self.多引脚模板_示例.主流程分支(
            输入数值A=输入数值A,
            输入数值B=输入数值B,
            说明文本=说明文本,
        ):
            case "正向分支":
                pass
            case "非正向分支":
                pass

        # 再根据外部的分支值走多分支流程出口，向外层暴露 3 个流程出口
        match self.多分支_示例_类格式.按整数多分支(分支值=分支值):
            case "分支为0":
                流程出("分支为0")
            case "分支为1":
                流程出("分支为1")
            case "分支为其他":
                流程出("分支为其他")

        # 对外数据输出：复用内层“多引脚模板”的返回值语义
        求和结果 = 加法运算(self.game, 左值=输入数值A, 右值=输入数值B)
        描述回声_句柄, 描述回声 = 获取局部变量(self.game, 初始值=说明文本)
        return 求和结果, 描述回声


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

