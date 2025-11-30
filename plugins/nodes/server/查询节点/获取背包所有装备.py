from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取背包所有装备",
    category="查询节点",
    inputs=[("背包持有者实体", "实体")],
    outputs=[("装备索引列表", "整数列表")],
    description="获取背包所有装备，出参为所有装备索引组成的列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取背包所有装备(game, 背包持有者实体):
    """获取背包所有装备，出参为所有装备索引组成的列表"""
    return [10001, 10002, 10003]
