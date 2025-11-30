from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体位置",
    category="查询节点",
    inputs=[("实体", "实体")],
    outputs=[("位置", "三维向量")],
    description="获取指定实体的位置",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取实体位置(game, 实体):
    """获取指定实体的位置"""
    entity_id = game._get_entity_id(实体)
    entity = game.get_entity(entity_id)
    if entity:
        return entity.position
    return [0, 0, 0]
