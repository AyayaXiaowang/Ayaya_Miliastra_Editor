from __future__ import annotations

import math

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询角色当前移动速度",
    category="查询节点",
    inputs=[("角色实体", "实体")],
    outputs=[("当前速度", "浮点数"), ("速度向量", "三维向量")],
    description="仅当角色拥有【监听移动速率】的单位状态效果时，才能查询",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询角色当前移动速度(game, 角色实体):
    """仅当角色拥有【监听移动速率】的单位状态效果时，才能查询"""
    get_entity_id = getattr(game, "_get_entity_id", None)
    entity_id = str(get_entity_id(角色实体)) if callable(get_entity_id) else str(getattr(角色实体, "entity_id", None) or 角色实体)

    get_entity = getattr(game, "get_entity", None)
    ent = get_entity(entity_id) if callable(get_entity) else 角色实体
    if ent is None:
        return 0.0, [0.0, 0.0, 0.0]

    vel = getattr(ent, "velocity", None)
    if vel is None:
        get_custom = getattr(game, "get_custom_variable", None)
        if callable(get_custom):
            vel = get_custom(ent, "速度向量", None)
    if vel is None:
        vel = [0.0, 0.0, 0.0]

    vx, vy, vz = vel
    speed = math.sqrt(float(vx) * float(vx) + float(vy) * float(vy) + float(vz) * float(vz))

    get_custom = getattr(game, "get_custom_variable", None)
    if callable(get_custom):
        override = get_custom(ent, "当前速度", None)
        if override is not None:
            speed = float(override)

    return float(speed), [float(vx), float(vy), float(vz)]
