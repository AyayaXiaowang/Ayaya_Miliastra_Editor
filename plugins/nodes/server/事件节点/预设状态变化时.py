from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="预设状态变化时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("预设状态索引", "整数"), ("变化前值", "整数"), ("变化后值", "整数")],
    description="节点图所关联的实体的预设状态发生变化时，触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 预设状态变化时(game):
    """节点图所关联的实体的预设状态发生变化时，触发该事件"""
    事件源 = game.get_entity("self")
    return 事件源, "self_guid", 0, False, True
