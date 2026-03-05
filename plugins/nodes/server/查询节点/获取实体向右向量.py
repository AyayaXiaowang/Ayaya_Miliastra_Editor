from __future__ import annotations

import math

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体向右向量",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("向右向量", "三维向量")],
    description="获取指定实体的向右向量（即该实体本地坐标系下的x轴正方向朝向）",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取实体向右向量(game, 目标实体):
    """获取指定实体的向右向量（即该实体本地坐标系下的x轴正方向朝向）"""
    get_entity_id = getattr(game, "_get_entity_id", None)
    entity_id = str(get_entity_id(目标实体)) if callable(get_entity_id) else str(getattr(目标实体, "entity_id", None) or 目标实体)

    get_entity = getattr(game, "get_entity", None)
    ent = get_entity(entity_id) if callable(get_entity) else 目标实体
    if ent is None:
        return [1.0, 0.0, 0.0]

    _pitch_deg, yaw_deg, _roll_deg = ent.rotation
    yaw = math.radians(float(yaw_deg))
    cy = math.cos(yaw)
    sy = math.sin(yaw)

    # 最小语义：忽略 roll/pitch，仅基于 yaw 计算水平右方向。
    return [float(cy), 0.0, float(-sy)]
