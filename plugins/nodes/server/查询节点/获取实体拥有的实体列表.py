from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体拥有的实体列表",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("实体列表", "实体列表")],
    description="获取所有以目标实体为拥有者的实体组成的列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取实体拥有的实体列表(game, 目标实体):
    """获取所有以目标实体为拥有者的实体组成的列表"""
    get_entity_id = getattr(game, "_get_entity_id", None)
    target_id = str(get_entity_id(目标实体)) if callable(get_entity_id) else str(getattr(目标实体, "entity_id", None) or 目标实体)

    get_all_entities = getattr(game, "get_all_entities", None)
    if callable(get_all_entities):
        all_entities = list(get_all_entities())
    else:
        all_entities = list(getattr(game, "entities", {}).values())

    get_custom = getattr(game, "get_custom_variable", None)
    out = []
    for ent in all_entities:
        owner_id = getattr(ent, "owner_entity_id", None)
        if owner_id is None and callable(get_custom):
            owner_id = get_custom(ent, "owner_entity_id", None)
        if owner_id is None:
            continue
        if str(owner_id) == target_id:
            out.append(ent)
    return out
