"""
composite_id: composite_多引脚模板_示例__演示项目
node_name: 多引脚模板_示例
node_description: 展示多流程入/出与多数据入/出的复合节点骨架，可直接复制后填充业务逻辑
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

from app.runtime.engine.graph_prelude_server import *
from engine.nodes.composite_spec import composite_class, flow_entry

if TYPE_CHECKING:
    from engine.graph.composite.pin_api import 流程入, 流程出, 数据入, 数据出


# 节点图 DSL 的类型注解使用中文类型字符串（例如 "浮点数"/"整数"），而非 Python typing。
ZERO_FLOAT: "浮点数" = 0.0


@composite_class
class 多引脚模板_示例:
    """多引脚复合节点模板

    特性：
    - 2 个流程入口方法，均带流程入与流程出
    - 提供多数据入、多数据出示例，便于照抄扩展
    - 内部示例逻辑保持简单，可直接替换为业务节点
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 主流程分支(
        self,
        输入数值A: "浮点数",
        输入数值B: "浮点数",
        说明文本: "字符串",
    ):
        """示例流程入口：计算与分支选择"""
        流程入("主流程入口")
        数据入("输入数值A", pin_type="浮点数")
        数据入("输入数值B", pin_type="浮点数")
        数据入("说明文本", pin_type="字符串")
        数据出("求和结果", pin_type="浮点数", variable="求和结果")
        数据出("描述回声", pin_type="字符串", variable="描述回声")

        # 注意：部分基础节点输出端口为“泛型”，需要显式中文类型注解以确定端口类型。
        求和结果: "浮点数" = 加法运算(self.game, 左值=输入数值A, 右值=输入数值B)
        描述回声_局部变量句柄, 描述回声 = 获取局部变量(self.game, 初始值=说明文本)

        数值是否为正 = 数值大于(self.game, 左值=求和结果, 右值=ZERO_FLOAT)
        if 数值是否为正:
            流程出("正向分支")
        else:
            流程出("非正向分支")

        return 求和结果, 描述回声

    @flow_entry()
    def 辅助流程检查(
        self,
        输入列表: "整数列表",
        默认整数: "整数",
    ):
        """示例流程入口：处理列表并返回数据"""
        流程入("辅助流程入口")
        数据入("输入列表", pin_type="整数列表")
        数据入("默认整数", pin_type="整数")
        数据出("列表首元素", pin_type="整数", variable="列表首元素")
        数据出("列表长度", pin_type="整数", variable="列表长度")

        列表长度 = 获取列表长度(self.game, 列表=输入列表)
        是否有元素 = 数值大于(self.game, 左值=列表长度, 右值=0)

        if 是否有元素:
            列表首元素: "整数" = 获取列表对应值(self.game, 列表=输入列表, 序号=0)
            流程出("列表非空")
        else:
            列表首元素 = 默认整数
            流程出("列表为空")

        return 列表首元素, 列表长度


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
