"""
graph_id: server_template_complex_flow_example_01
graph_name: 模板示例_复杂控制流综合测试
graph_type: server
description: 模板示例：在“实体创建时”中结合 range 循环、列表迭代、break、嵌套多分支与布尔条件，演示复杂控制流写法并便于可视化调试。

节点图变量：
- 最终标记: 字符串 = "未完成"
- 观察列表: 字符串列表 = []
- 随机路径: 字符串 = "未定"
"""

# 最小化导入：使用本目录下的 _prelude 透出运行时与占位类型
import sys
import pathlib
from _prelude import *
from engine.graph.models.package_model import GraphVariableConfig

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="最终标记",
        variable_type="字符串",
        default_value="未完成",
        description="记录综合测试最终标记状态",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="观察列表",
        variable_type="字符串列表",
        default_value=[],
        description="记录 range 循环中每一步的计数文本，便于观察控制流",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="随机路径",
        variable_type="字符串",
        default_value="未定",
        description="记录随机分支路径（A/B/C 等）",
        is_exposed=False,
    ),
]


class 模板示例_复杂控制流综合测试:
    """演示在一张图内组合多种控制流写法的模板示例。

    - match / 双分支：嵌套混合
    - for 循环：range 循环与列表迭代循环均含 break
    - 数据/查询输出均被使用，避免未使用输出
    - 全部条件均为布尔节点或布尔表达式
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        # 自动验证节点图代码规范
        from app.runtime.engine.node_graph_validator import validate_node_graph
        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """事件：实体创建时（入口）。在本示例中用于串联多种控制流写法并将结果写回节点图变量，便于在编辑器中观察。"""
        设置节点图变量(self.game, 变量名="最终标记", 变量值="初始化", 是否触发事件=False)

        # 1) 顶层 match：随机路径
        随机值 = 获取随机整数(self.game, 下限=0, 上限=3)
        match 随机值:
            case 0:
                设置节点图变量(self.game, 变量名="随机路径", 变量值="A", 是否触发事件=False)
            case 1:
                设置节点图变量(self.game, 变量名="随机路径", 变量值="B", 是否触发事件=False)
            case _:
                设置节点图变量(self.game, 变量名="随机路径", 变量值="C", 是否触发事件=False)

        # 2) range 循环（含 break）：当 计数 > 2 则跳出循环
        for 计数 in range(0, 5):
            是否大于二 = 数值大于(self.game, 左值=计数, 右值=2)
            if 是否大于二:
                break
            # 观察列表：以字符串记录计数（示例包含数值节点 + 类型转换）
            计数偏移值: "整数" = 加法运算(self.game, 左值=计数, 右值=1)
            计数文本: "字符串" = 数据类型转换(self.game, 输入=计数偏移值)
            观察列表_值: "字符串列表" = 拼装列表(self.game, "N", 计数文本)
            设置节点图变量(self.game, 变量名="观察列表", 变量值=观察列表_值, 是否触发事件=False)

        # 3) 列表迭代循环（含 break）
        候选: "字符串列表" = 拼装列表(self.game, "A", "B", "C", "D")
        for 项 in 候选:
            命中C = 是否相等(self.game, 枚举1=项, 枚举2="C")
            if 命中C:
                break
            # 非 C 的元素写入提示
            设置节点图变量(self.game, 变量名="随机路径", 变量值=项, 是否触发事件=False)

        # 4) 嵌套双分支 + match
        标志1 = 是否相等(self.game, 枚举1="X", 枚举2="Y")
        if 标志1:
            内部随机 = 获取随机整数(self.game, 下限=0, 上限=1)
            match 内部随机:
                case 0:
                    设置节点图变量(self.game, 变量名="最终标记", 变量值="内部分支0", 是否触发事件=False)
                case _:
                    设置节点图变量(self.game, 变量名="最终标记", 变量值="内部分支1", 是否触发事件=False)
        else:
            条件2 = 逻辑与运算(self.game, 输入1=True, 输入2=False)
            if 条件2:
                设置节点图变量(self.game, 变量名="最终标记", 变量值="外部分支-AND", 是否触发事件=False)
            else:
                设置节点图变量(self.game, 变量名="最终标记", 变量值="外部分支-ELSE", 是否触发事件=False)

        # 5) 完结
        设置节点图变量(self.game, 变量名="最终标记", 变量值="复杂流完成", 是否触发事件=True)

    def register_handlers(self):
        """注册所有事件处理器"""
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)





if __name__ == "__main__":
    # 允许“直接运行该脚本”触发对自身的节点图规范自检
    # 输出：通过/未通过 + 错误/警告明细
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

    # 非严格退出：仅在未通过时使用非零退出码，便于CI/批量校验
    if not 是否通过:
        # 使用系统退出码 1 表示校验失败
        sys.exit(1)
