from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="以GUID查询实体",
    category="查询节点",
    inputs=[("GUID", "GUID")],
    outputs=[("实体", "实体")],
    description="根据GUID查询实体",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 以GUID查询实体(game, GUID):
    """根据GUID查询实体"""
    return game.get_entity(GUID)
