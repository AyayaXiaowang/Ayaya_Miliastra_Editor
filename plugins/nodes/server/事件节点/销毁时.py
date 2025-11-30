from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="实体移除/销毁时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源GUID", "GUID")],
    description="关卡内任意实体被移除或销毁时触发该事件，该事件仅在关卡实体上可以触发 实体被销毁或被移除均会触发该事件。因此实体被销毁时，会依次触发【实体销毁时】以及【实体移除/销毁时】事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 实体移除销毁时(game):
    """关卡内任意实体被移除或销毁时触发该事件，该事件仅在关卡实体上可以触发 实体被销毁或被移除均会触发该事件。因此实体被销毁时，会依次触发【实体销毁时】以及【实体移除/销毁时】事件"""
    return "removed_entity_guid"
