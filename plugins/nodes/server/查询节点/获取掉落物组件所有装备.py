from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取掉落物组件所有装备",
    category="查询节点",
    inputs=[("掉落物实体", "实体")],
    outputs=[("装备索引列表", "整数列表")],
    description="获取掉落物元件上掉落物组件中的所有装备",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取掉落物组件所有装备(game, 掉落物实体):
    """获取掉落物元件上掉落物组件中的所有装备"""
    return [10004]
