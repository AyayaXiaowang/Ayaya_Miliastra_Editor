from __future__ import annotations

import math

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体向前向量",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("向前向量", "三维向量")],
    description="获取指定实体的向前向量（即该实体本地坐标系下的z轴正方向朝向）",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取实体向前向量(game, 目标实体):
    """获取指定实体的向前向量（即该实体本地坐标系下的z轴正方向朝向）"""
    get_entity_id = getattr(game, "_get_entity_id", None)
    entity_id = str(get_entity_id(目标实体)) if callable(get_entity_id) else str(getattr(目标实体, "entity_id", None) or 目标实体)

    get_entity = getattr(game, "get_entity", None)
    ent = get_entity(entity_id) if callable(get_entity) else 目标实体
    if ent is None:
        return [0.0, 0.0, 1.0]

    pitch_deg, yaw_deg, _roll_deg = ent.rotation
    pitch = math.radians(float(pitch_deg))
    yaw = math.radians(float(yaw_deg))

    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cy = math.cos(yaw)
    sy = math.sin(yaw)

    # 约定：旋转为 [pitch, yaw, roll]（角度）；向前 = 本地 z 轴正方向在世界坐标下的朝向。
    return [float(sy * cp), float(-sp), float(cy * cp)]
