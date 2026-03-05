"""
composite_id: composite_TS_列表字典写入_v1
node_name: TS_列表字典写入_v1
node_description: 回归测试：覆盖写回侧支持的列表类型与字典（VarType=27）复合节点虚拟引脚落盘，并包含字典查询节点以固化 K/V 语义证据。
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
class TS_列表字典写入_v1:
    """列表 + 字典虚拟引脚写入覆盖（用于 `.gil` 写回/进游戏验收）。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 写入_列表与字典(
        self,
        整数列表: "整数列表",
        字符串列表: "字符串列表",
        GUID列表: "GUID列表",
        布尔列表: "布尔值列表",
        浮点列表: "浮点数列表",
        向量列表: "三维向量列表",
        配置ID列表: "配置ID列表",
        元件ID列表: "元件ID列表",
        阵营列表: "阵营列表",
        字典_字符串到整数: "字符串-整数字典",
    ):
        流程入("流程入")
        数据入("整数列表", pin_type="整数列表")
        数据入("字符串列表", pin_type="字符串列表")
        数据入("GUID列表", pin_type="GUID列表")
        数据入("布尔列表", pin_type="布尔值列表")
        数据入("浮点列表", pin_type="浮点数列表")
        数据入("向量列表", pin_type="三维向量列表")
        数据入("配置ID列表", pin_type="配置ID列表")
        数据入("元件ID列表", pin_type="元件ID列表")
        数据入("阵营列表", pin_type="阵营列表")
        数据入("字典_字符串到整数", pin_type="字符串-整数字典")

        数据出("整数列表长度", pin_type="整数", variable="整数列表长度")
        数据出("字典示例值", pin_type="整数", variable="字典示例值")
        数据出("列表长度列表", pin_type="整数列表", variable="列表长度列表")

        打印字符串(self.game, 字符串="TS_列表字典写入_v1.写入_列表与字典")

        # 关键：这些列表入参在语义上属于“接口覆盖”，即使不参与最终返回，也必须在子图中被节点显式消费；
        # 否则会因 mapped_ports=0 在 UI/写回/导出侧被视为“未使用”而不渲染，导致测试集看起来像“缺引脚”。
        字符串列表长度 = 获取列表长度(self.game, 列表=字符串列表)
        GUID列表长度 = 获取列表长度(self.game, 列表=GUID列表)
        布尔列表长度 = 获取列表长度(self.game, 列表=布尔列表)
        浮点列表长度 = 获取列表长度(self.game, 列表=浮点列表)
        向量列表长度 = 获取列表长度(self.game, 列表=向量列表)
        配置ID列表长度 = 获取列表长度(self.game, 列表=配置ID列表)
        元件ID列表长度 = 获取列表长度(self.game, 列表=元件ID列表)
        阵营列表长度 = 获取列表长度(self.game, 列表=阵营列表)

        整数列表长度 = 获取列表长度(self.game, 列表=整数列表)
        列表长度列表 = 拼装列表(
            self.game,
            字符串列表长度,
            GUID列表长度,
            布尔列表长度,
            浮点列表长度,
            向量列表长度,
            配置ID列表长度,
            元件ID列表长度,
            阵营列表长度,
        )
        字典示例值: "整数" = 以键查询字典值(self.game, 字典=字典_字符串到整数, 键="a", 默认值=0)
        流程出("流程出")
        return 整数列表长度, 字典示例值, 列表长度列表


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

