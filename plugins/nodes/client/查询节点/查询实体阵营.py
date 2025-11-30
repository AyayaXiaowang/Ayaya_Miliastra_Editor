from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询实体阵营",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("阵营", "阵营")],
    description="查询目标实体的阵营",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 查询实体阵营(game, 目标实体):
    """查询目标实体的阵营"""
    return None  # 阵营
