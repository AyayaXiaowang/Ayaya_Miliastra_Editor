from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="以实体查询GUID",
    category="查询节点",
    inputs=[("实体", "实体")],
    outputs=[("GUID", "GUID")],
    description="查询指定实体的GUID",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 以实体查询GUID(game, 实体):
    """查询指定实体的GUID"""
    return None  # GUID
