from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询自身是否已入战",
    category="查询节点",
    outputs=[("是否入战", "布尔值")],
    description="查询该节点图关联的实体是否入战",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 查询自身是否已入战():
    """查询该节点图关联的实体是否入战"""
    return None  # 是否入战
