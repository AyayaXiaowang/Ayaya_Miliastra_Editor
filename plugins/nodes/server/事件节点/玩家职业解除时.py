from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="玩家职业解除时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("更改前职业配置ID", "配置ID"), ("更改后职业配置ID", "配置ID")],
    description="玩家职业解除时触发该事件发送给对应玩家，可以在更改前职业的职业节点图里收到",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 玩家职业解除时(game):
    """玩家职业解除时触发该事件发送给对应玩家，可以在更改前职业的职业节点图里收到"""
    玩家 = game.create_mock_entity("玩家")
    return 玩家, "玩家_guid", "旧职业ID", "新职业ID"
