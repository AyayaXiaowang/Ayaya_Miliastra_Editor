from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="实体阵营变化时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("变化前阵营", "阵营"), ("变化后阵营", "阵营")],
    description="实体的阵营变化时，触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 实体阵营变化时(game):
    """实体的阵营变化时，触发该事件"""
    事件源 = game.get_entity("entity_1")
    return 事件源, "mock_guid_003", 1, 2
