from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="三维向量内积",
    category="运算节点",
    inputs=[("三维向量1", "三维向量"), ("三维向量2", "三维向量")],
    outputs=[("结果", "浮点数")],
    description="计算两个输入三维向量的内积（点乘）",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 三维向量内积(game, 三维向量1, 三维向量2):
    """计算两个输入三维向量的内积（点乘）"""
    x1, y1, z1 = 三维向量1[0], 三维向量1[1], 三维向量1[2]
    x2, y2, z2 = 三维向量2[0], 三维向量2[1], 三维向量2[2]
    return x1*x2 + y1*y2 + z1*z2
