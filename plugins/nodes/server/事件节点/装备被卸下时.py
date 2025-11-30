from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="装备被卸下时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("装备持有者实体", "实体"), ("装备持有者GUID", "GUID"), ("装备索引", "整数")],
    description="装备被卸下时触发该事件，装备的持有者可以收到，需要配置在道具节点图里",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 装备被卸下时(game):
    """装备被卸下时触发该事件，装备的持有者可以收到，需要配置在道具节点图里"""
    持有者 = game.create_mock_entity("玩家")
    return 持有者, "玩家_guid", 10001
