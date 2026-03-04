"""
composite_id: composite_实体列表_按评分取TopK
node_name: 实体列表_按评分取前K
node_description: 根据评分列表从实体列表中选出前 K 个（评分越大越靠前），输出实体列表与序号列表
scope: server
"""

# Python 等价写法：
# - 有效长度 = min(len(输入实体列表), len(评分列表))
# - 序号列表 = sorted(range(有效长度), key=lambda i: 评分列表[i], reverse=True)[:TopK数量]
# - TopK实体列表 = [输入实体列表[i] for i in 序号列表]
#
# 示例输入输出：
# - 输入实体列表=[实体A, 实体B, 实体C], 评分列表=[0.2, 0.9, 0.5], TopK数量=2 -> TopK实体列表=[实体B, 实体C], TopK序号列表=[1, 2]
#
# Graph Code 调用示例（server，语法糖：直接写复合节点名(...)；多数据出用“元组赋值”承接）：
# - TopK实体列表, TopK序号列表 = 实体列表_按评分取前K(输入实体列表=输入实体列表, 评分列表=评分列表, TopK数量=TopK数量)

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
class 实体列表_按评分取前K:
    """实体列表按评分取前 K（从大到小）"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    @flow_entry()
    def 选择(self, 输入实体列表: "实体列表", 评分列表: "浮点数列表", TopK数量: "整数"):
        """按评分从大到小选择 TopK；有效长度按两列表较短者裁剪。"""
        流程入("流程入")
        数据入("输入实体列表", pin_type="实体列表")
        数据入("评分列表", pin_type="浮点数列表")
        数据入("TopK数量", pin_type="整数")
        数据出("TopK实体列表", pin_type="实体列表", variable="TopK实体列表")
        数据出("TopK序号列表", pin_type="整数列表", variable="TopK序号列表")

        # 注意：Graph Code 的端口类型推断以“赋值上的中文类型注解”为主；
        # 仅写在函数签名上的类型注解不一定能覆盖所有推断场景，因此这里显式落盘一次。
        输入实体列表_入参: "实体列表" = 输入实体列表
        评分列表_入参: "浮点数列表" = 评分列表
        TopK数量_入参: "整数" = TopK数量

        _, 实体列表值 = 获取局部变量(self.game, 初始值=输入实体列表_入参)
        _, 评分列表值 = 获取局部变量(self.game, 初始值=评分列表_入参)
        TopK数量 = TopK数量_入参

        实体长度: "整数" = 获取列表长度(self.game, 列表=实体列表值)
        评分长度: "整数" = 获取列表长度(self.game, 列表=评分列表值)

        有效长度句柄, 有效长度 = 获取局部变量(self.game, 初始值=评分长度)
        实体更短: "布尔值" = 数值小于(self.game, 左值=实体长度, 右值=评分长度)
        if 实体更短:
            设置局部变量(self.game, 局部变量=有效长度句柄, 值=实体长度)

        TopK数量裁剪: "整数" = 范围限制运算(self.game, 输入=TopK数量, 下限=0, 上限=有效长度)

        TopK实体列表: "实体列表" = [self.owner_entity]
        清除列表(self.game, 列表=TopK实体列表)

        TopK序号列表: "整数列表" = [0]
        清除列表(self.game, 列表=TopK序号列表)

        已选序号列表: "整数列表" = [0]
        清除列表(self.game, 列表=已选序号列表)

        for _外层计数 in range(TopK数量裁剪):
            是否找到候选句柄, 是否找到候选 = 获取局部变量(self.game, 初始值=False)
            最佳序号句柄, 最佳序号 = 获取局部变量(self.game, 初始值=0)
            最佳评分句柄, 最佳评分 = 获取局部变量(self.game, 初始值=0.0 + 0.0)

            for 候选序号 in range(有效长度):
                是否已选中: "布尔值" = 列表是否包含该值(self.game, 列表=已选序号列表, 值=候选序号)
                if not 是否已选中:
                    候选评分: "浮点数" = 获取列表对应值(self.game, 列表=评分列表值, 序号=候选序号)

                    if not 是否找到候选:
                        设置局部变量(self.game, 局部变量=是否找到候选句柄, 值=True)
                        设置局部变量(self.game, 局部变量=最佳序号句柄, 值=候选序号)
                        设置局部变量(self.game, 局部变量=最佳评分句柄, 值=候选评分)
                    else:
                        是否更好: "布尔值" = 数值大于(self.game, 左值=候选评分, 右值=最佳评分)
                        if 是否更好:
                            设置局部变量(self.game, 局部变量=最佳序号句柄, 值=候选序号)
                            设置局部变量(self.game, 局部变量=最佳评分句柄, 值=候选评分)

            if 是否找到候选:
                对列表插入值(self.game, 列表=已选序号列表, 插入序号=999999, 插入值=最佳序号)
                对列表插入值(self.game, 列表=TopK序号列表, 插入序号=999999, 插入值=最佳序号)

                最佳实体: "实体" = 获取列表对应值(self.game, 列表=实体列表值, 序号=最佳序号)
                对列表插入值(self.game, 列表=TopK实体列表, 插入序号=999999, 插入值=最佳实体)

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


