from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="三维向量：下方",
    category="查询节点",
    outputs=[("(0,-1,0)", "三维向量")],
    description="返回(0,-1,0)",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 三维向量_下方():
    """返回(0,-1,0)"""
    return [0, -1, 0]
