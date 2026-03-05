"""
graph_id: server_template_complex_flow_example_01__测试基础内容
graph_name: 测试_复杂控制流综合测试
graph_type: server
description: 测试节点图（控制流回归）：在“实体创建时”中组合 range 循环、列表迭代、break、match-case、多层 if-else 与布尔表达式，并将关键中间值写回节点图变量，便于在编辑器中可视化观察与回归。

节点图变量：
- 最终标记: 字符串 = "未完成"
- 观察列表: 字符串列表 = []
- 随机路径: 字符串 = "未定"
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir()))
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / 'assets'))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403

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

class 测试_复杂控制流综合测试:
    """演示在一张图内组合多种控制流写法的模板示例。

    - match / 双分支：嵌套混合
    - for 循环：range 循环与列表迭代循环均含 break
    - 数据/查询输出均被使用，避免未使用输出
    - 分支条件均为布尔节点或布尔表达式
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
            是否大于二 = 计数 > 2
            if 是否大于二:
                break
            # 观察列表：以字符串记录计数（示例包含数值节点 + 类型转换）
            计数偏移值: "整数" = 计数 + 1
            计数文本: "字符串" = str(计数偏移值)
            观察列表_值: "字符串列表" = ["N", 计数文本]
            设置节点图变量(self.game, 变量名="观察列表", 变量值=观察列表_值, 是否触发事件=False)

        # 3) 列表迭代循环（含 break）
        候选: "字符串列表" = ["A", "B", "C", "D"]
        for 项 in 候选:
            if 项 == "C":
                break
            # 非 C 的元素写入提示
            设置节点图变量(self.game, 变量名="随机路径", 变量值=项, 是否触发事件=False)

        # 4) 嵌套双分支 + match
        标志1 = "X" == "Y"
        if 标志1:
            内部随机 = 获取随机整数(self.game, 下限=0, 上限=1)
            match 内部随机:
                case 0:
                    设置节点图变量(self.game, 变量名="最终标记", 变量值="内部分支0", 是否触发事件=False)
                case _:
                    设置节点图变量(self.game, 变量名="最终标记", 变量值="内部分支1", 是否触发事件=False)
        else:
            条件2 = True and False
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
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))