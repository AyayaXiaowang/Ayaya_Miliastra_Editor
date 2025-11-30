from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="根据装备索引查询装备配置ID",
    category="查询节点",
    inputs=[("装备索引", "整数")],
    outputs=[("装备配置ID", "配置ID")],
    description="根据装备索引查询装备配置ID，装备实例的索引可以在【装备初始化】事件中获取到",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 根据装备索引查询装备配置ID(game, 装备索引):
    """根据装备索引查询装备配置ID，装备实例的索引可以在【装备初始化】事件中获取到"""
    return "装备ID_001"
