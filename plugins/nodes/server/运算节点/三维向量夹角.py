from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="三维向量夹角",
    category="运算节点",
    inputs=[("三维向量1", "三维向量"), ("三维向量2", "三维向量")],
    outputs=[("夹角(弧度)", "浮点数")],
    description="计算两个三维向量之间的夹角，以弧度输出",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 三维向量夹角(game, 三维向量1, 三维向量2):
    """计算两个三维向量之间的夹角，以弧度输出"""
    import math
    # 计算点积
    dot = 三维向量内积(game, 三维向量1, 三维向量2)
    # 计算模长
    len1 = 三维向量模运算(game, 三维向量1)
    len2 = 三维向量模运算(game, 三维向量2)
    # 避免除零
    if len1 == 0 or len2 == 0:
        return 0
    # cos(θ) = dot / (len1 * len2)
    cos_angle = dot / (len1 * len2)
    # 限制范围到[-1, 1]避免精度问题
    cos_angle = max(-1, min(1, cos_angle))
    return math.acos(cos_angle)
