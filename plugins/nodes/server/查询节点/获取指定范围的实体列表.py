from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取指定范围的实体列表",
    category="查询节点",
    inputs=[("目标实体列表", "实体列表"), ("中心点", "三维向量"), ("半径", "浮点数")],
    outputs=[("结果列表", "实体列表")],
    description="在目标实体列表中获取指定球形范围内的实体列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取指定范围的实体列表(game, 目标实体列表, 中心点, 半径):
    """在目标实体列表中获取指定球形范围内的实体列表"""
    cx, cy, cz = 中心点
    r = float(半径)
    r2 = r * r

    get_entity_id = getattr(game, "_get_entity_id", None)
    get_entity = getattr(game, "get_entity", None)

    out = []
    for item in list(目标实体列表 or []):
        entity_id = str(get_entity_id(item)) if callable(get_entity_id) else str(getattr(item, "entity_id", None) or item)
        ent = get_entity(entity_id) if callable(get_entity) else item
        if ent is None:
            continue

        x, y, z = ent.position
        dx = float(x) - float(cx)
        dy = float(y) - float(cy)
        dz = float(z) - float(cz)
        if (dx * dx + dy * dy + dz * dz) <= r2:
            out.append(ent)
    return out
