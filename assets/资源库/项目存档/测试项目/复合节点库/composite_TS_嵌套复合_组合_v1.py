"""
composite_id: composite_TS_嵌套复合_组合_v1
node_name: TS_嵌套复合_组合_v1
node_description: 回归测试：复合节点内部调用其它复合节点（嵌套复合）+ 复合内发送信号，用于验证递归收集与 section10 注入。
scope: server
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

_workspace_root = next(
    directory for directory in Path(__file__).resolve().parents if (directory / "pyrightconfig.json").is_file()
)
_workspace_root_text = str(_workspace_root)
if _workspace_root_text not in sys.path:
    sys.path.insert(0, _workspace_root_text)

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403
from engine.nodes.composite_spec import composite_class, flow_entry

from 资源库.项目存档.测试项目.复合节点库.composite_TS_全类型写入_v1 import TS_全类型写入_v1
from 资源库.项目存档.测试项目.复合节点库.composite_TS_复合内发送信号_v1 import TS_复合内发送信号_v1
from 资源库.项目存档.测试项目.复合节点库.composite_TS_合并引脚_扇出_v1 import TS_合并引脚_扇出_v1

if TYPE_CHECKING:
    from engine.graph.composite.pin_api import 流程入, 流程出, 数据入, 数据出


@composite_class
class TS_嵌套复合_组合_v1:
    """嵌套复合组合：复合内调用复合，覆盖递归打包。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        self.TS_全类型写入_v1 = TS_全类型写入_v1(game, owner_entity)
        self.TS_复合内发送信号_v1 = TS_复合内发送信号_v1(game, owner_entity)
        self.TS_合并引脚_扇出_v1 = TS_合并引脚_扇出_v1(game, owner_entity)

    @flow_entry()
    def 组合流程(self, 数值: "浮点数", 文本: "字符串", 事件GUID: "GUID", 事件实体: "实体"):
        流程入("流程入")
        数据入("数值", pin_type="浮点数")
        数据入("文本", pin_type="字符串")
        数据入("事件GUID", pin_type="GUID")
        数据入("事件实体", pin_type="实体")
        数据出("双倍", pin_type="浮点数", variable="双倍")

        # 复合节点校验口径：外部数据入需在子图中形成可建模的数据依赖。
        # 对“仅用于驱动嵌套复合调用”的入参，先通过【获取局部变量】生成稳定的数据来源节点。
        _h_num, 数值_局部 = 获取局部变量(self.game, 初始值=数值)
        _h_text, 文本_局部 = 获取局部变量(self.game, 初始值=文本)
        _h_guid, 事件GUID_局部 = 获取局部变量(self.game, 初始值=事件GUID)
        _h_ent, 事件实体_局部 = 获取局部变量(self.game, 初始值=事件实体)

        打印字符串(self.game, 字符串="TS_嵌套复合_组合_v1.组合流程")

        # 1) 调用合并引脚复合（扇出）
        双倍, _平方 = self.TS_合并引脚_扇出_v1.扇出_双倍与平方(数值=数值_局部)

        # 2) 调用全类型写入复合（用事件实体/GUID 作为输入，避免依赖外部 registry 常量）
        self.TS_全类型写入_v1.写入_标量与ID(
            整数值=1,
            浮点值=数值_局部,
            布尔值=True,
            文本=文本_局部,
            输入GUID=事件GUID_局部,
            输入实体=事件实体_局部,
            输入阵营=0,
            输入配置ID=1,
            输入元件ID=1,
            输入向量=(0.0, 1.0, 2.0),
        )

        # 3) 复合内发送信号（嵌套链路）
        self.TS_复合内发送信号_v1.触发_全类型信号(
            数字A=7,
            数字B=数值_局部,
            文本=文本_局部,
            是否启用=True,
            关联GUID=事件GUID_局部,
        )

        流程出("流程出")
        return 双倍


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

