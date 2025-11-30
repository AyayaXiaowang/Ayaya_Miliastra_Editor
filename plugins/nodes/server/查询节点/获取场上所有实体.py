from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取场上所有实体",
    category="查询节点",
    outputs=[("实体列表", "实体列表")],
    description="获取当前场上所有在场的实体，该实体列表的数量可能会较大",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取场上所有实体(game):
    """获取当前场上所有在场的实体，该实体列表的数量可能会较大"""
    return list(game.entities.values())
