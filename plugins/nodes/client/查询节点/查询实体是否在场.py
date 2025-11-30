from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询实体是否在场",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("是否在场", "布尔值")],
    description="查询指定实体是否在场 注意角色实体即使处于倒下状态，仍然认为在场",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 查询实体是否在场(game, 目标实体):
    """查询指定实体是否在场 注意角色实体即使处于倒下状态，仍然认为在场"""
    entity_id = game._get_entity_id(目标实体)
    return entity_id in game.entities
