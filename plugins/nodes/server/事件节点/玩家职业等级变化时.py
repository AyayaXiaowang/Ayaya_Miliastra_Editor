from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="玩家职业等级变化时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("变化前等级", "整数"), ("变化后等级", "整数")],
    description="玩家职业等级变化时触发该事件发送给对应玩家，可以在该职业的职业节点图里收到",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 玩家职业等级变化时(game):
    """玩家职业等级变化时触发该事件发送给对应玩家，可以在该职业的职业节点图里收到"""
    玩家 = game.create_mock_entity("玩家1")
    return 玩家, "player_guid", 1, 2
