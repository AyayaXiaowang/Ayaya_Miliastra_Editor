from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询装备标签列表",
    category="查询节点",
    inputs=[("装备索引", "整数")],
    outputs=[("标签列表", "配置ID列表")],
    description="查询该装备实例的所有标签组成的列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询装备标签列表(game, 装备索引):
    """查询该装备实例的所有标签组成的列表"""
    return ["传说", "武器"]
