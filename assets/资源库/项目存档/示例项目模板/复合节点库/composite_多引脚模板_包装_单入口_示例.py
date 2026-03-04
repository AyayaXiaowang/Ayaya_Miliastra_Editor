"""
composite_id: composite_多引脚模板_包装_单入口_示例
node_name: 多引脚模板_包装_单入口_示例
node_description: 将“多引脚模板_示例”的两个流程入口包装为一个单入口复合节点，便于在宿主图中稳定调用与导出测试
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

from 资源库.项目存档.示例项目模板.复合节点库.composite_多引脚模板_示例 import 多引脚模板_示例

if TYPE_CHECKING:
    from engine.graph.composite.pin_api import 流程入, 流程出, 数据入, 数据出


@composite_class
class 多引脚模板_包装_单入口_示例:
    """单入口包装：覆盖“多引脚模板_示例”的两个入口方法。

    设计目的：
    - 宿主图侧的严格校验与导出链路更偏好“单流程入口”的复合节点；
    - 这里用包装层把两个入口都“实际连线并执行一遍”，从而覆盖内部多入口实现，同时对宿主图只暴露一个入口。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.多引脚模板_示例 = 多引脚模板_示例(game, owner_entity)

    @flow_entry()
    def 执行一次组合流程(
        self,
        输入数值A: "浮点数",
        输入数值B: "浮点数",
        说明文本: "字符串",
        输入列表: "整数列表",
        默认整数: "整数",
    ):
        流程入("流程入")
        数据入("输入数值A", pin_type="浮点数")
        数据入("输入数值B", pin_type="浮点数")
        数据入("说明文本", pin_type="字符串")
        数据入("输入列表", pin_type="整数列表")
        数据入("默认整数", pin_type="整数")

        数据出("求和结果", pin_type="浮点数", variable="求和结果")
        数据出("描述回声", pin_type="字符串", variable="描述回声")
        数据出("列表首元素", pin_type="整数", variable="列表首元素")
        数据出("列表长度", pin_type="整数", variable="列表长度")

        # 入口1：辅助流程（列表）
        match self.多引脚模板_示例.辅助流程检查(输入列表=输入列表, 默认整数=默认整数):
            case "列表非空":
                pass
            case "列表为空":
                pass

        # 入口2：主流程（数值+文本）——以其流程出口作为外层主要分支输出
        match self.多引脚模板_示例.主流程分支(
            输入数值A=输入数值A,
            输入数值B=输入数值B,
            说明文本=说明文本,
        ):
            case "正向分支":
                流程出("正向分支")
            case "非正向分支":
                流程出("非正向分支")

        # 输出数据：按与内层语义一致的节点调用生成（避免依赖“返回值绑定”的跨层细节）
        求和结果 = 加法运算(self.game, 左值=输入数值A, 右值=输入数值B)
        描述回声_句柄, 描述回声 = 获取局部变量(self.game, 初始值=说明文本)

        列表长度 = 获取列表长度(列表=输入列表)
        列表首元素 = 获取列表对应值(列表=输入列表, 序号=0)

        return 求和结果, 描述回声, 列表首元素, 列表长度


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

