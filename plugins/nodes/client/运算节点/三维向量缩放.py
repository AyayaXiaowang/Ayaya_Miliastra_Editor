from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="三维向量缩放",
    category="运算节点",
    inputs=[("缩放倍率", "浮点数"), ("三维向量", "三维向量")],
    outputs=[("结果", "三维向量")],
    description="将输入的三维向量缩放后输出（三维向量数乘）",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 三维向量缩放(缩放倍率, 三维向量):
    """将输入的三维向量缩放后输出（三维向量数乘）"""
    x, y, z = 三维向量[0], 三维向量[1], 三维向量[2]
    return [x * 缩放倍率, y * 缩放倍率, z * 缩放倍率]
