from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取阵营结算排名数值",
    category="查询节点",
    inputs=[("阵营", "阵营")],
    outputs=[("排名数值", "整数")],
    description="获取指定阵营结算的排名数值",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取阵营结算排名数值(game, 阵营):
    """获取指定阵营结算的排名数值"""
    return 1
