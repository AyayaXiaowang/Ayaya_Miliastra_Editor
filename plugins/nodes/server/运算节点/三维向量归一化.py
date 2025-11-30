from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="三维向量归一化",
    category="运算节点",
    inputs=[("三维向量", "三维向量")],
    outputs=[("结果", "三维向量")],
    description="将三维向量的长度归一化后输出",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 三维向量归一化(game, 三维向量):
    """将三维向量的长度归一化后输出"""
    x, y, z = 三维向量
    length = math.sqrt(x*x + y*y + z*z)
    if length == 0:
        return [0, 0, 0]
    return [x/length, y/length, z/length]
