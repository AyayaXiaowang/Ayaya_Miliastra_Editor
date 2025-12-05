"""
graph_id: server_template_loop_iterate_int_list
graph_name: 模板示例_循环遍历整数列表
graph_type: server
description: 基础示例：在“实体创建时”构造一个整数列表，使用 for 循环遍历并累加总和，演示【for 循环 + 节点函数】组合用法。

节点图变量：
- 调试_列表长度: 整数 = 0
- 调试_元素总和: 整数 = 0
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
        name="调试_列表长度",
        variable_type="整数",
        default_value=0,
        description="记录示例整数列表的长度，便于在编辑器中观察。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_元素总和",
        variable_type="整数",
        default_value=0,
        description="记录示例整数列表中所有元素求和的结果，便于在编辑器中观察。",
        is_exposed=False,
    ),
]


class 模板示例_循环遍历整数列表:
    """演示在节点图中结合 Python for 循环与节点函数遍历列表的最小用法。

    用法约定：
    - 本图挂载在任意 server 侧实体上，在【实体创建时】事件中运行一次；
    - 通过【拼装列表】节点构造一个整数列表；
    - 使用 for 循环逐个访问列表元素，在循环体内用【加法运算】累加总和；
    - 循环结束后，将“列表长度”和“元素总和”写入节点图变量，方便在编辑器中观察。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """实体创建完毕后，构造一个整数列表并用 for 循环遍历一次。"""
        整数列表示例值: "整数列表" = 拼装列表(
            self.game,
            1,
            2,
            3,
            4,
            5,
        )

        列表长度局部变量句柄, 当前循环次数 = 获取局部变量(
            self.game,
            初始值=0,
        )
        元素总和局部变量句柄, 当前总和 = 获取局部变量(
            self.game,
            初始值=0,
        )

        for 当前元素 in 整数列表示例值:
            新总和: "整数" = 加法运算(
                self.game,
                左值=当前总和,
                右值=当前元素,
            )
            设置局部变量(
                self.game,
                局部变量=元素总和局部变量句柄,
                值=新总和,
            )
            当前总和 = 新总和

            新循环次数: "整数" = 加法运算(
                self.game,
                左值=当前循环次数,
                右值=1,
            )
            设置局部变量(
                self.game,
                局部变量=列表长度局部变量句柄,
                值=新循环次数,
            )
            当前循环次数 = 新循环次数

        设置节点图变量(
            self.game,
            变量名="调试_列表长度",
            变量值=当前循环次数,
            是否触发事件=False,
        )
        设置节点图变量(
            self.game,
            变量名="调试_元素总和",
            变量值=当前总和,
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
    from runtime.engine.node_graph_validator import validate_file

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


