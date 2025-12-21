"""
graph_id: server_struct_all_types_example_01
graph_name: 模板示例_结构体全类型_拆分与拼装
graph_type: server
description: 使用 struct_all_supported_types_example 结构体演示【拼装结构体】/【拆分结构体】/【修改结构体】的基础用法：在实体创建时拼装一个覆盖全部字段类型的结构体写入自定义变量，再拆分读取并通过别名变量串联，最后在结算事件中演示如何修改单个字段。

节点图变量：
- 调试_最近一次结构体实例: 结构体 = None
- 调试_整数字段镜像: 整数 = 0
- 调试_字符串字段镜像: 字符串 = ""
- 调试_布尔值字段镜像: 布尔值 = False
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
        name="调试_最近一次结构体实例",
        variable_type="结构体",
        default_value=None,
        description="记录最近一次通过【拼装结构体】构造的结构体实例，便于在编辑器中查看全部字段值。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_整数字段镜像",
        variable_type="整数",
        default_value=0,
        description="镜像 struct_all_supported_types_example.整数字段 的数值，便于在编辑器中观察。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_字符串字段镜像",
        variable_type="字符串",
        default_value="",
        description="镜像 struct_all_supported_types_example.字符串字段 的文本内容。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_布尔值字段镜像",
        variable_type="布尔值",
        default_value=False,
        description="镜像 struct_all_supported_types_example.布尔值字段 的布尔状态。",
        is_exposed=False,
    ),
]


class 模板示例_结构体全类型_拆分与拼装:
    """演示结构体系统全字段类型用法的模板示例。

    用法约定：
    - 结构体定义 `struct_all_supported_types_example` 已在“管理配置/结构体定义”中作为【基础结构体】存在；
    - 本图挂载在任意实体上，在【实体创建时】事件中通过【拼装结构体】节点将各字段值拼装为一个结构体实例，
      并写入该实体的自定义变量（例如变量名 `示例_全类型结构体`）；
    - 随后通过【拆分结构体】节点从该实例中拆分出若干代表性的字段（整数/字符串/布尔值），将它们镜像到
      节点图变量 `调试_整数字段镜像` / `调试_字符串字段镜像` / `调试_布尔值字段镜像`，方便在编辑器中观察；
    - 在另一个事件【自定义变量变化时】中，通过【修改结构体】节点演示如何只更新结构体中的单个字段：
      - 将整数字段加一后写回自定义变量；
      - 同时再次拆分结构体并刷新调试镜像变量。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """在实体创建时构造一个覆盖主要字段类型的结构体实例并写入自定义变量。"""
        自身实体: "实体" = 获取自身实体(self.game)

        # 在真实节点图中，此处对应一颗绑定 `struct_all_supported_types_example` 的【拼装结构体】节点，
        # 每个字段在图中都有一个同名的数据输入端口，这里通过关键字参数直观地表达这些端口。
        结构体实例: "结构体" = 拼装结构体(
            self.game,
            结构体名="struct_all_supported_types_example",
            实体字段=自身实体,
            GUID字段="123456789",
            整数字段=1,
            布尔值字段=True,
            浮点数字段=3.14,
            字符串字段="示例_结构体全类型",
        )

        设置自定义变量(
            self.game,
            目标实体=自身实体,
            变量名="示例_全类型结构体",
            变量值=结构体实例,
            是否触发事件=False,
        )

        # 为了方便在编辑器中直接看到当前结构体实例，也将其镜像到节点图变量中。
        设置节点图变量(
            self.game,
            变量名="调试_最近一次结构体实例",
            变量值=结构体实例,
            是否触发事件=False,
        )

        # 在真实图中，此处应通过【拆分结构体】节点拆出感兴趣的字段：
        # - 绑定同一个基础结构体 `struct_all_supported_types_example`；
        # - 在“配置结构体与字段”对话框中勾选需要作为输出端口暴露的字段；
        # - 图编辑器会根据绑定信息为该节点增加与字段同名的输出端口。
        #
        # 这里调用一次【拆分结构体】节点函数，并直接按字段顺序解包输出，
        # 与图中“拆分节点的多个数据出口被连到后续节点”的形态保持一致。
        实体字段, GUID字段, 整数字段, 布尔值字段, 浮点数字段, 字符串字段 = 拆分结构体(
            self.game,
            结构体名="struct_all_supported_types_example",
            结构体实例=结构体实例,
        )

        # 下游节点中使用“拆分后”的字段值：在实际图中，相当于从【拆分结构体】节点的输出端口
        # 接出若干连线到后续节点；这里通过“解包输出 + 别名变量”的方式表达这些数据通路。
        实体字段当前值: "实体" = 实体字段
        GUID字段当前值: "GUID" = GUID字段
        整数字段当前值: "整数" = 整数字段
        字符串字段当前值: "字符串" = 字符串字段
        布尔值字段当前值: "布尔值" = 布尔值字段
        浮点数字段当前值: "浮点数" = 浮点数字段



        设置节点图变量(self.game, 变量名="调试_整数字段镜像", 变量值=整数字段当前值, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_字符串字段镜像", 变量值=字符串字段当前值, 是否触发事件=False)
        设置节点图变量(self.game, 变量名="调试_布尔值字段镜像", 变量值=布尔值字段当前值, 是否触发事件=False)

    # ---------------------------- 事件：自定义变量变化时 ----------------------------
    def on_自定义变量变化时(self, 事件源实体, 事件源GUID, 变量名, 变化前值, 变化后值):
        """当自定义变量 `示例_请求递增整数字段` 变为 True 时，演示如何只修改结构体中的一个字段。"""
        变量名值: "字符串" = 变量名
        是递增请求: "布尔值" = 是否相等(
            self.game,
            输入1=变量名值,
            输入2="示例_请求递增整数字段",
        )
        if 是递增请求:
            pass
        else:
            return

        请求值: "布尔值" = 变化后值
        if 请求值:
            pass
        else:
            # 仅在 False -> True 翻转时处理
            return

        目标实体: "实体" = 事件源实体
        当前结构体实例: "结构体" = 获取自定义变量(
            self.game,
            目标实体=目标实体,
            变量名="示例_全类型结构体",
        )

        # 在真实节点图中，这一步应通过【拆分结构体】节点读取字段值，而不是把结构体当作字典用【以键查询字典值】读取。
        实体字段_修改前, GUID字段_修改前, 整数字段_修改前, 布尔值字段_修改前, 浮点数字段_修改前, 字符串字段_修改前 = 拆分结构体(
            self.game,
            结构体名="struct_all_supported_types_example",
            结构体实例=当前结构体实例,
        )
        当前整数字段值: "整数" = 整数字段_修改前
        新整数字段值: "整数" = 加法运算(
            self.game,
            左值=当前整数字段值,
            右值=1,
        )

        # 在真实节点图中，这一步对应一颗绑定 `struct_all_supported_types_example` 的【修改结构体】节点，
        # 仅勾选“整数字段”作为需要修改的字段，其它字段保持不变。
        修改结构体(
            self.game,
            结构体名="struct_all_supported_types_example",
            结构体实例=当前结构体实例,
            整数字段=新整数字段值,
        )

        设置自定义变量(
            self.game,
            目标实体=目标实体,
            变量名="示例_全类型结构体",
            变量值=当前结构体实例,
            是否触发事件=False,
        )

        写回后结构体实例: "结构体" = 获取自定义变量(
            self.game,
            目标实体=目标实体,
            变量名="示例_全类型结构体",
        )
        设置节点图变量(
            self.game,
            变量名="调试_最近一次结构体实例",
            变量值=写回后结构体实例,
            是否触发事件=False,
        )

        实体字段_修改后, GUID字段_修改后, 整数字段_修改后, 布尔值字段_修改后, 浮点数字段_修改后, 字符串字段_修改后 = 拆分结构体(
            self.game,
            结构体名="struct_all_supported_types_example",
            结构体实例=写回后结构体实例,
        )
        最新整数字段值: "整数" = 整数字段_修改后
        设置节点图变量(self.game, 变量名="调试_整数字段镜像", 变量值=最新整数字段值, 是否触发事件=False)

    # ---------------------------- 注册事件处理器 ----------------------------
    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "自定义变量变化时",
            self.on_自定义变量变化时,
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



