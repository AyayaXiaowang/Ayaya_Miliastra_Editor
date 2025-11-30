from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="造物入战时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID")],
    description="仅在经典仇恨模式生效 造物入战时触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 造物入战时(game):
    """仅在经典仇恨模式生效 造物入战时触发该事件"""
    造物 = game.create_mock_entity("造物")
    return 造物, "造物_guid"
