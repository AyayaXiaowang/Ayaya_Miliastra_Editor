"""
graph_id: server_template_shared_composite_nodes_sugar_demo_02
graph_name: 模板示例_共享复合节点扩展语法糖
graph_type: server
description: 示例节点图（共享复合节点语法糖扩展）：演示“直接写复合节点名(...)”的写法，解析器会自动注入实例并改写为复合节点调用（无需手动实例化；示例不写回节点图变量）。
"""

import sys
from pathlib import Path

PROJECT_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir()))
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / 'assets'))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403

class 模板示例_共享复合节点扩展语法糖:
    """共享复合节点语法糖扩展示例（server）"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # 示例输入：不使用节点图变量，直接在方法内声明输入。
        输入整数列表: "整数列表" = [10, 20, 30]
        整数保留条件列表: "布尔值列表" = [True, False, True]
        权重列表: "浮点数列表" = [0.2, 0.8]
        评分列表: "浮点数列表" = [0.2, 0.9]

        # 1) 列表过滤（按布尔掩码）
        过滤后整数列表: "整数列表" = 整数列表_按布尔掩码过滤(
            输入列表=输入整数列表,
            保留条件列表=整数保留条件列表,
        )

        示例实体列表: "实体列表" = [self.owner_entity, 事件源实体]
        实体保留条件列表: "布尔值列表" = [True, False]
        过滤后实体列表: "实体列表" = 实体列表_按布尔掩码过滤(
            输入列表=示例实体列表,
            保留条件列表=实体保留条件列表,
        )

        # 2) 查找首次出现序号（多数据出：元组赋值承接）
        整数是否找到, 整数首次序号 = 整数列表_查找首次出现序号(
            输入列表=输入整数列表,
            目标值=20,
        )

        实体是否找到, 实体首次序号 = 实体列表_查找首次出现序号(
            输入列表=示例实体列表,
            目标实体=事件源实体,
        )

        # 3) 权重随机（序号 / 实体）
        随机序号是否成功, 随机选中序号 = 权重列表_随机选序号(权重列表=权重列表)

        随机实体是否成功, 随机实体序号, 随机实体 = 实体列表_按权重随机选实体(
            输入实体列表=示例实体列表,
            权重列表=权重列表,
        )

        # 4) 冷却检查（并更新时间戳）
        当前时间戳: "整数" = 查询时间戳_UTC_0时区(self.game)

        冷却是否就绪, 更新后上次触发时间戳 = 冷却_检查并更新时间戳(
            当前时间戳=当前时间戳,
            上次触发时间戳=0,
            冷却秒数=5,
        )

        # 5) 统计 / 分组
        整数频次字典: "整数-整数字典" = 整数列表_统计出现次数(输入列表=输入整数列表)

        分组键列表: "整数列表" = [1, 1, 2]
        整数分组字典: "整数-整数列表字典" = 整数列表_按键分组(输入列表=输入整数列表, 分组键列表=分组键列表)

        # 6) TopK（按评分取前 K）
        TopK实体列表, TopK序号列表 = 实体列表_按评分取前K(
            输入实体列表=示例实体列表,
            评分列表=评分列表,
            TopK数量=1,
        )

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)

if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))
