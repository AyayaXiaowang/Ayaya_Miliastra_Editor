from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询实体阵营",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("阵营", "阵营")],
    description="查询指定实体的阵营",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询实体阵营(game, 目标实体):
    """查询指定实体的阵营"""
    return 1
