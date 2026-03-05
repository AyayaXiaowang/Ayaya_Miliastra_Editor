"""
graph_id: server_template_shared_composite_nodes_demo_01
graph_name: 模板示例_共享复合节点调用
graph_type: server
description: 示例节点图（Python 原生语法 → 自动复合节点）：演示如何直接写 Python 原生语法（切片/sum/any/all/三元表达式），由编译器自动转换为对应复合节点（示例不写回节点图变量）。
"""

import sys
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir()))
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / 'assets'))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403

class 模板示例_共享复合节点调用:
    """Python 原生语法 → 自动复合节点示例

    目标：
    - 演示“节点图脚本直接写 Python 原生语法（切片/sum/any/all/三元表达式）”；
    - 演示“由编译器自动映射到对应复合节点/基础节点实现（无需手动 import/实例化复合节点类）”；
    - 示例不读写节点图变量，仅展示“写法如何被解析/改写”。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 示例输入：不使用节点图变量，直接在方法内声明输入。
        输入整数列表: "整数列表" = [1, 2, 3, 4, 5]

        # 1) 整数列表切片（Python 原生切片语法，会自动转换为对应复合节点）
        切片结果列表: "整数列表" = 输入整数列表[1:4]

        # 2) 整数列表求和（Python 原生 sum(...)，会自动转换为对应复合节点）
        切片结果总和: "整数" = sum(切片结果列表)

        # 3) any/all（布尔值列表聚合）
        是否总和大于3: "布尔值" = 切片结果总和 > 3
        是否总和等于0: "布尔值" = 切片结果总和 == 0
        示例布尔值列表: "布尔值列表" = [是否总和大于3, 是否总和等于0]

        任意为真结果: "布尔值" = any(示例布尔值列表)
        全部为真结果: "布尔值" = all(示例布尔值列表)

        # 4) 条件选择（Python 原生三元表达式，会自动转换为对应复合节点）
        条件选择整数结果: "整数" = 切片结果总和 if 任意为真结果 else 0
        条件选择浮点结果: "浮点数" = 1.25 if 全部为真结果 else 0.5

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)

if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))
