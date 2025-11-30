from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="三维向量夹角",
    category="运算节点",
    inputs=[("三维向量1", "三维向量"), ("三维向量2", "三维向量")],
    outputs=[("夹角角度", "浮点数")],
    description="计算两个三维向量之间的夹角，以角度输出",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 三维向量夹角(三维向量1, 三维向量2):
    """计算两个三维向量之间的夹角，以角度输出"""
    # 计算点积和模
    dot = 三维向量内积(三维向量1, 三维向量2)
    len1 = 三维向量模运算(三维向量1)
    len2 = 三维向量模运算(三维向量2)
    
    if len1 == 0 or len2 == 0:
        return 0
    
    # cos(θ) = dot / (len1 * len2)
    cos_angle = dot / (len1 * len2)
    # 防止浮点误差导致的超出[-1, 1]范围
    cos_angle = max(-1, min(1, cos_angle))
    # 返回角度
    return math.degrees(math.acos(cos_angle))
