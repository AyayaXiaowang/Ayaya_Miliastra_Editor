from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取装备词条配置ID",
    category="查询节点",
    inputs=[("装备索引", "整数"), ("词条序号", "整数")],
    outputs=[("词条配置ID", "配置ID")],
    description="根据装备实例上装备词条的序号获取该词条的配置ID",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取装备词条配置ID(game, 装备索引, 词条序号):
    """根据装备实例上装备词条的序号获取该词条的配置ID"""
    return "词条ID_攻击力"
