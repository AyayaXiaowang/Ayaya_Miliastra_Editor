from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取拥有者实体",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("拥有者实体", "实体")],
    description="获取指定目标实体的拥有者实体",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取拥有者实体(game, 目标实体):
    """获取指定目标实体的拥有者实体"""
    get_entity_id = getattr(game, "_get_entity_id", None)
    entity_id = str(get_entity_id(目标实体)) if callable(get_entity_id) else str(getattr(目标实体, "entity_id", None) or 目标实体)

    get_entity = getattr(game, "get_entity", None)
    ent = get_entity(entity_id) if callable(get_entity) else 目标实体
    if ent is None:
        return None

    # 最小语义：优先读取实体上的 owner 引用/owner_entity_id；其次允许通过自定义变量注入 owner_entity_id。
    direct_owner = getattr(ent, "owner", None)
    if direct_owner is not None:
        return direct_owner

    owner_id = getattr(ent, "owner_entity_id", None)
    if owner_id is None:
        get_custom = getattr(game, "get_custom_variable", None)
        if callable(get_custom):
            owner_id = get_custom(ent, "owner_entity_id", None)
    if owner_id is None:
        return None
    return get_entity(str(owner_id)) if callable(get_entity) else None
