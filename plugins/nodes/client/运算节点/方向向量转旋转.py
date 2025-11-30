from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="方向向量转旋转",
    category="运算节点",
    inputs=[("向前向量", "三维向量"), ("向上向量", "三维向量")],
    outputs=[("旋转", "三维向量")],
    description="给定向前向量和向上向量，转化为欧拉角",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 方向向量转旋转(game, 向前向量, 向上向量):
    """给定向前向量和向上向量，转化为欧拉角"""
    import math
    x, y, z = 向前向量[0], 向前向量[1], 向前向量[2]
    yaw = math.atan2(x, z)
    pitch = math.atan2(-y, math.sqrt(x*x + z*z))
    return [math.degrees(pitch), math.degrees(yaw), 0]
