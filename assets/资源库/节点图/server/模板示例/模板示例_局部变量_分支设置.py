"""
graph_id: server_template_local_variable_branch_assign
graph_name: 模板示例_局部变量_分支设置
graph_type: server
description: 基础示例：在“实体创建时”中使用【获取局部变量→设置局部变量】在 if-else 分支中多次修改同一个局部变量，并将最终结果写入节点图变量。

节点图变量：
- 调试_分支索引: 整数 = 0
- 调试_最终结果: 整数 = 0
"""

from __future__ import annotations

import sys
import pathlib

脚本文件路径 = pathlib.Path(__file__).resolve()
节点图根目录 = 脚本文件路径.parents[2]  # 节点图根目录（.../节点图）
服务器节点图目录 = 节点图根目录 / "server"  # 包含 server 侧 `_prelude.py` 的目录
if str(服务器节点图目录) not in sys.path:
    sys.path.insert(0, str(服务器节点图目录))

from _prelude import *
from engine.graph.models.package_model import GraphVariableConfig


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="调试_分支索引",
        variable_type="整数",
        default_value=0,
        description="记录本次随机选择的分支索引，便于在编辑器中观察。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_最终结果",
        variable_type="整数",
        default_value=0,
        description="记录根据分支写入的最终局部变量值，便于在编辑器中观察。",
        is_exposed=False,
    ),
]


class 模板示例_局部变量_分支设置:
    """演示在 if-else 分支中多次修改同一个局部变量的最小用法。

    用法约定：
    - 本图挂载在任意 server 侧实体上，在【实体创建时】事件中运行一次；
    - 首先使用【获取随机整数】随机生成一个分支索引，写入节点图变量；
    - 然后使用【获取局部变量(初始值=0)】获得局部结果的句柄与当前值；
    - 在 if-else 分支中通过【设置局部变量】分别写入不同的值；
    - 事件结束前将当前值写入节点图变量，方便在编辑器中观察。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """实体创建完毕后，随机选择一个分支，并在分支中多次设置同一个局部变量。"""
        分支索引: "整数" = 获取随机整数(
            self.game,
            下限=0,
            上限=1,
        )
        设置节点图变量(
            self.game,
            变量名="调试_分支索引",
            变量值=分支索引,
            是否触发事件=False,
        )

        局部结果句柄, 当前结果值 = 获取局部变量(
            self.game,
            初始值=0,
        )

        是否走第一个分支 = 是否相等(
            self.game,
            输入1=分支索引,
            输入2=0,
        )
        if 是否走第一个分支:
            当前结果值: "整数" = 加法运算(
                self.game,
                左值=0,
                右值=10,
            )
            设置局部变量(
                self.game,
                局部变量=局部结果句柄,
                值=当前结果值,
            )
        else:
            当前结果值: "整数" = 加法运算(
                self.game,
                左值=0,
                右值=20,
            )
            设置局部变量(
                self.game,
                局部变量=局部结果句柄,
                值=当前结果值,
            )

        设置节点图变量(
            self.game,
            变量名="调试_最终结果",
            变量值=当前结果值,
            是否触发事件=False,
        )

    # ---------------------------- 注册事件处理器 ----------------------------
    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file

    自身文件路径 = pathlib.Path(__file__).resolve()
    是否通过, 错误列表, 警告列表 = validate_file(自身文件路径)
    print("=" * 80)
    print(f"节点图自检: {自身文件路径.name}")
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


