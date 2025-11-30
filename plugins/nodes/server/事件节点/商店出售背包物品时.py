from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="商店出售背包物品时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("商店持有者", "实体"), ("商店持有者GUID", "GUID"), ("购买者实体", "实体"), ("商店序号", "整数"), ("道具配置ID", "配置ID"), ("购买数量", "整数")],
    description="商店出售背包物品时触发，商店组件的持有者可收到",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 商店出售背包物品时(game):
    """商店出售背包物品时触发，商店组件的持有者可收到"""
    商店持有者 = game.create_mock_entity("商店NPC")
    购买者 = game.create_mock_entity("玩家")
    return 商店持有者, "商店_guid", 购买者, 0, "道具ID_001", 5
