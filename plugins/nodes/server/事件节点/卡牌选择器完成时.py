from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="卡牌选择器完成时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("目标玩家", "实体"), ("选择结果列表", "整数列表"), ("完成原因", "枚举"), ("卡牌选择器索引", "整数")],
    description="玩家操作完成卡牌选择器/或者因为时间原因强制关闭等，都会给玩家节点图触发本事件 出参可以通知本次卡牌选择器的结果，和对应原因",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 卡牌选择器完成时(game):
    """玩家操作完成卡牌选择器/或者因为时间原因强制关闭等，都会给玩家节点图触发本事件 出参可以通知本次卡牌选择器的结果，和对应原因"""
    玩家 = game.create_mock_entity("玩家")
    return 玩家, [1, 3, 5], "玩家确认", 0
