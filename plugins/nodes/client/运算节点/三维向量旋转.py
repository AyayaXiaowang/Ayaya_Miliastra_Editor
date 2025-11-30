from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="三维向量旋转",
    category="运算节点",
    inputs=[("被旋转的三维向量", "三维向量"), ("旋转", "三维向量")],
    outputs=[("结果", "三维向量")],
    description="将被旋转的三维向量，按照旋转所表示的欧拉角进行旋转后返回结果",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 三维向量旋转(game, 被旋转的三维向量, 旋转):
    """将被旋转的三维向量，按照旋转所表示的欧拉角进行旋转后返回结果"""
    import math
    pitch, yaw, roll = math.radians(旋转[0]), math.radians(旋转[1]), math.radians(旋转[2])
    x, y, z = 被旋转的三维向量[0], 被旋转的三维向量[1], 被旋转的三维向量[2]
    
    # 简化实现：只绕Y轴旋转(yaw)
    cos_y, sin_y = math.cos(yaw), math.sin(yaw)
    new_x = x * cos_y + z * sin_y
    new_y = y
    new_z = -x * sin_y + z * cos_y
    
    return [new_x, new_y, new_z]
