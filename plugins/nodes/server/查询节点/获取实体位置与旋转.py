from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体位置与旋转",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("位置", "三维向量"), ("旋转", "三维向量")],
    description="获取目标实体的位置和旋转 对玩家实体和关卡实体无意义",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取实体位置与旋转(game, 目标实体):
    """获取目标实体的位置和旋转 对玩家实体和关卡实体无意义"""
    entity_id = game._get_entity_id(目标实体)
    entity = game.get_entity(entity_id)
    if entity:
        return entity.position, entity.rotation
    return [0, 0, 0], [0, 0, 0]
