from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="拆分三维向量",
    category="运算节点",
    inputs=[("三维向量", "三维向量")],
    outputs=[("X分量", "浮点数"), ("Y分量", "浮点数"), ("Z分量", "浮点数")],
    description="将三维向量的x、y、z分量输出为三个浮点数",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 拆分三维向量(三维向量):
    """将三维向量的x、y、z分量输出为三个浮点数"""
    if isinstance(三维向量, (list, tuple)) and len(三维向量) >= 3:
        return 三维向量[0], 三维向量[1], 三维向量[2]
    return 0, 0, 0
