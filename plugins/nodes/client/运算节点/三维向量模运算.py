from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="三维向量模运算",
    category="运算节点",
    inputs=[("三维向量", "三维向量")],
    outputs=[("结果", "浮点数")],
    description="计算输入三维向量的模",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 三维向量模运算(三维向量):
    """计算输入三维向量的模"""
    x, y, z = 三维向量[0], 三维向量[1], 三维向量[2]
    return math.sqrt(x*x + y*y + z*z)
