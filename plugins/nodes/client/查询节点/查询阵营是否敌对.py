from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询阵营是否敌对",
    category="查询节点",
    inputs=[("阵营1", "阵营"), ("阵营2", "阵营")],
    outputs=[("是否敌对", "布尔值")],
    description="查询阵营1和阵营2是否敌对",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 查询阵营是否敌对(阵营1, 阵营2):
    """查询阵营1和阵营2是否敌对"""
    return None  # 是否敌对
