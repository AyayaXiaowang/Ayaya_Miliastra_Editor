"""
graph_id: server_template_kill_count_victory_01
graph_name: 模板示例_击杀计数_达10胜利
graph_type: server
description: 示例节点图（击杀计数达标胜利）：挂在【敌方角色实体】上监听【角色倒下时】事件，为击倒者所属玩家的“击杀数”自定义变量 +1；当击杀数达到阈值（默认 10）后，设置该玩家结算状态为“胜利”并触发【结算关卡】。
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
        name="胜利所需击杀数",
        variable_type="整数",
        default_value=10,
        description="对外暴露：当玩家击杀数达到该值时判定胜利并触发关卡结算。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="玩家击杀数变量名",
        variable_type="字符串",
        default_value="击杀数",
        description="对外暴露：写入到玩家实体自定义变量中的击杀数变量名。",
        is_exposed=True,
    ),
]

class 模板示例_击杀计数_达10胜利:
    """击杀计数示例（单位死亡→击杀数+1→达标胜利）。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：角色倒下时 ----------------------------
    def on_角色倒下时(self, 角色实体, 原因, 击倒者实体):
        """敌方角色倒下时：为击倒者所属玩家的击杀数 +1；达标后触发胜利结算。"""

        玩家实体: "实体" = 获取角色归属的玩家实体(self.game, 角色实体=击倒者实体)
        玩家击杀数变量名: "字符串" = 获取节点图变量(self.game, 变量名="玩家击杀数变量名")

        当前击杀数: "整数" = 获取自定义变量(
            self.game,
            目标实体=玩家实体,
            变量名=玩家击杀数变量名,
        )
        新击杀数: "整数" = 当前击杀数 + 1

        胜利所需击杀数: "整数" = 获取节点图变量(self.game, 变量名="胜利所需击杀数")
        达到胜利条件: "布尔值" = 新击杀数 >= 胜利所需击杀数
        if 达到胜利条件:
            # 说明（兼容拉取式模拟器）：
            # - 在“每次取数据都会回溯重算”的模拟执行器中，如果先【设置自定义变量】再进入【双分支】，
            #   会导致分支条件回溯时再次读取已更新的击杀数，从而出现 +2 的非预期行为。
            # - 因此本示例采用“先判定分支，再写入击杀数”的结构：即使模拟器不做节点输出缓存，也能保证击杀数只 +1。
            设置自定义变量(
                self.game,
                目标实体=玩家实体,
                变量名=玩家击杀数变量名,
                变量值=新击杀数,
                是否触发事件=False,
            )
            设置玩家结算成功状态(
                self.game,
                玩家实体=玩家实体,
                结算状态="胜利",
            )
            结算关卡(self.game)
            return

        设置自定义变量(
            self.game,
            目标实体=玩家实体,
            变量名=玩家击杀数变量名,
            变量值=新击杀数,
            是否触发事件=False,
        )

    # ---------------------------- 注册事件处理器 ----------------------------
    def register_handlers(self):
        # 注意：根据挂载规则，“角色倒下时”只能挂在【角色实体】上触发。
        self.game.register_event_handler("角色倒下时", self.on_角色倒下时, owner=self.owner_entity)

if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli
    raise SystemExit(validate_file_cli(__file__))
