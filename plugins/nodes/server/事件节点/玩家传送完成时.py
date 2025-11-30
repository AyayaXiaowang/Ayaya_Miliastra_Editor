from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="玩家传送完成时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("玩家实体", "实体"), ("玩家GUID", "GUID")],
    description="玩家传送完成时，在玩家实体的节点图上可以触发该事件 玩家首次进入关卡时，也会触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 玩家传送完成时(game):
    """玩家传送完成时，在玩家实体的节点图上可以触发该事件 玩家首次进入关卡时，也会触发该事件"""
    玩家 = game.create_mock_entity("玩家1")
    return 玩家, "player_guid_001"
