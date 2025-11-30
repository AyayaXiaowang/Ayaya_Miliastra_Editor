from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="三维向量模运算",
    category="运算节点",
    inputs=[("三维向量", "三维向量")],
    outputs=[("结果", "浮点数")],
    description="计算输入的三维向量的模",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 三维向量模运算(game, 三维向量):
    """计算输入的三维向量的模"""
    x, y, z = 三维向量[0], 三维向量[1], 三维向量[2]
    return math.sqrt(x*x + y*y + z*z)
