from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="角色复苏时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("角色实体", "实体")],
    description="角色复苏时，角色实体上的的节点图可以触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 角色复苏时(game):
    """角色复苏时，角色实体上的的节点图可以触发该事件"""
    角色 = game.create_mock_entity("角色")
    return 角色
