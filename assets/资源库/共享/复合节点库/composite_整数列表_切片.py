"""
composite_id: composite_整数列表_切片
node_name: 整数列表_切片
node_description: 对整数列表执行切片（start 含，end 不含），用于替代不受支持的列表切片语法（列表[start:end]）
scope: server
"""

# Python 等价写法：
# - 结果列表 = 输入列表[开始序号:结束序号]
#
# 示例输入输出：
# - 输入列表=[1, 2, 3, 4, 5], 开始序号=1, 结束序号=4 -> 结果列表=[2, 3, 4]
#
# Graph Code 示例（推荐写法：语法糖，自动改写为共享复合节点）：
# - 结果列表: "整数列表" = 输入列表[开始序号:结束序号]
#
# Graph Code 调用示例（server，手动实例化）：
# - self._整数切片 = 整数列表_切片(self.game, self.owner_entity)
# - 结果列表: "整数列表" = self._整数切片.切片(输入列表=输入列表, 开始序号=开始序号, 结束序号=结束序号)

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
class 整数列表_切片:
    """整数列表切片

    约束与说明：
    - Graph Code 不支持 `列表[start:end]` 切片语法；
    - 本复合节点提供等价的“切片”逻辑，并支持负数序号（按 Python 约定从末尾反向计数）；
    - `start` 含、`end` 不含；越界会被裁剪到 [0, len]。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 切片(self, 输入列表: "整数列表", 开始序号: "整数", 结束序号: "整数"):
        """返回输入列表在 [开始序号, 结束序号) 区间内的子列表"""
        流程入("流程入")
        数据入("输入列表", pin_type="整数列表")
        数据入("开始序号", pin_type="整数")
        数据入("结束序号", pin_type="整数")
        数据出("结果列表", pin_type="整数列表", variable="结果列表")
        流程出("完成")

        # 注意：Graph Code 的端口类型推断以“赋值上的中文类型注解”为主；
        # 仅写在函数签名上的类型注解不一定能覆盖所有推断场景，因此这里显式落盘一次。
        输入列表_入参: "整数列表" = 输入列表
        开始序号_入参: "整数" = 开始序号
        结束序号_入参: "整数" = 结束序号

        输入列表句柄, 输入列表值 = 获取局部变量(self.game, 初始值=输入列表_入参)
        开始序号句柄, 开始序号值 = 获取局部变量(self.game, 初始值=开始序号_入参)
        结束序号句柄, 结束序号值 = 获取局部变量(self.game, 初始值=结束序号_入参)

        列表长度: "整数" = 获取列表长度(self.game, 列表=输入列表值)

        开始序号是否为负数: "布尔值" = 数值小于(self.game, 左值=开始序号值, 右值=0)
        结束序号是否为负数: "布尔值" = 数值小于(self.game, 左值=结束序号值, 右值=0)

        开始归一化句柄, 开始序号归一化 = 获取局部变量(self.game, 初始值=开始序号值)
        if 开始序号是否为负数:
            开始序号从末尾计算: "整数" = 加法运算(self.game, 左值=列表长度, 右值=开始序号值)
            设置局部变量(self.game, 局部变量=开始归一化句柄, 值=开始序号从末尾计算)

        结束归一化句柄, 结束序号归一化 = 获取局部变量(self.game, 初始值=结束序号值)
        if 结束序号是否为负数:
            结束序号从末尾计算: "整数" = 加法运算(self.game, 左值=列表长度, 右值=结束序号值)
            设置局部变量(self.game, 局部变量=结束归一化句柄, 值=结束序号从末尾计算)

        开始序号裁剪: "整数" = 范围限制运算(self.game, 输入=开始序号归一化, 下限=0, 上限=列表长度)
        结束序号裁剪: "整数" = 范围限制运算(self.game, 输入=结束序号归一化, 下限=0, 上限=列表长度)

        结束是否小于开始: "布尔值" = 数值小于(self.game, 左值=结束序号裁剪, 右值=开始序号裁剪)
        if 结束是否小于开始:
            结束序号裁剪 = 开始序号裁剪

        切片长度: "整数" = 减法运算(self.game, 左值=结束序号裁剪, 右值=开始序号裁剪)

        # 注意：列表字面量在 Graph Code 中会被改写为【拼装列表】节点调用；
        # 这里显式写为节点调用以强化类型推断（避免局部变量初始值被判定为“泛型”）。
        结果列表: "整数列表" = 拼装列表(self.game, 0)
        清除列表(self.game, 列表=结果列表)

        for 偏移序号 in range(切片长度):
            当前序号: "整数" = 加法运算(self.game, 左值=开始序号裁剪, 右值=偏移序号)
            当前元素: "整数" = 获取列表对应值(self.game, 列表=输入列表值, 序号=当前序号)
            对列表插入值(self.game, 列表=结果列表, 插入序号=999999, 插入值=当前元素)

        return 结果列表


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


