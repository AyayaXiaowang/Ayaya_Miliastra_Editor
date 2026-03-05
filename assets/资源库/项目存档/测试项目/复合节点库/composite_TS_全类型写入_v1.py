"""
composite_id: composite_TS_全类型写入_v1
node_name: TS_全类型写入_v1
node_description: 回归测试：覆盖写回侧支持的主要 VarType（标量/ID/阵营/向量）与复合节点虚拟引脚落盘；数据出通过“局部变量节点”避免透传违规。
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

if TYPE_CHECKING:
    from engine.graph.composite.pin_api import 流程入, 流程出, 数据入, 数据出


@composite_class
class TS_全类型写入_v1:
    """标量/ID/向量类虚拟引脚写入覆盖（用于 `.gil` 写回/进游戏验收）。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 写入_标量与ID(
        self,
        整数值: "整数",
        浮点值: "浮点数",
        布尔值: "布尔值",
        文本: "字符串",
        输入GUID: "GUID",
        输入实体: "实体",
        输入阵营: "阵营",
        输入配置ID: "配置ID",
        输入元件ID: "元件ID",
        输入向量: "三维向量",
    ):
        流程入("流程入")
        数据入("整数值", pin_type="整数")
        数据入("浮点值", pin_type="浮点数")
        数据入("布尔值", pin_type="布尔值")
        数据入("文本", pin_type="字符串")
        数据入("输入GUID", pin_type="GUID")
        数据入("输入实体", pin_type="实体")
        数据入("输入阵营", pin_type="阵营")
        数据入("输入配置ID", pin_type="配置ID")
        数据入("输入元件ID", pin_type="元件ID")
        数据入("输入向量", pin_type="三维向量")

        数据出("整数回声", pin_type="整数", variable="整数回声")
        数据出("浮点回声", pin_type="浮点数", variable="浮点回声")
        数据出("布尔回声", pin_type="布尔值", variable="布尔回声")
        数据出("文本回声", pin_type="字符串", variable="文本回声")
        数据出("GUID回声", pin_type="GUID", variable="GUID回声")
        数据出("实体回声", pin_type="实体", variable="实体回声")
        数据出("阵营回声", pin_type="阵营", variable="阵营回声")
        数据出("配置ID回声", pin_type="配置ID", variable="配置ID回声")
        数据出("元件ID回声", pin_type="元件ID", variable="元件ID回声")
        数据出("向量回声", pin_type="三维向量", variable="向量回声")

        打印字符串(self.game, 字符串="TS_全类型写入_v1.写入_标量与ID")

        # 复合节点校验口径：数据出不允许直接透传数据入（必须经由节点调用产生）。
        _h_int, 整数回声 = 获取局部变量(self.game, 初始值=整数值)
        _h_float, 浮点回声 = 获取局部变量(self.game, 初始值=浮点值)
        _h_bool, 布尔回声 = 获取局部变量(self.game, 初始值=布尔值)
        _h_text, 文本回声 = 获取局部变量(self.game, 初始值=文本)
        _h_guid, GUID回声 = 获取局部变量(self.game, 初始值=输入GUID)
        _h_ent, 实体回声 = 获取局部变量(self.game, 初始值=输入实体)
        _h_camp, 阵营回声 = 获取局部变量(self.game, 初始值=输入阵营)
        _h_cfg, 配置ID回声 = 获取局部变量(self.game, 初始值=输入配置ID)
        _h_comp, 元件ID回声 = 获取局部变量(self.game, 初始值=输入元件ID)
        _h_vec, 向量回声 = 获取局部变量(self.game, 初始值=输入向量)

        流程出("流程出")
        return (
            整数回声,
            浮点回声,
            布尔回声,
            文本回声,
            GUID回声,
            实体回声,
            阵营回声,
            配置ID回声,
            元件ID回声,
            向量回声,
        )


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

