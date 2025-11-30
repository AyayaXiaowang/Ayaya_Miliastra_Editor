from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="三维向量：零向量",
    category="查询节点",
    outputs=[("(0,0,0)", "三维向量")],
    description="返回(0,0,0)",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 三维向量_零向量():
    """返回(0,0,0)"""
    return [0, 0, 0]
