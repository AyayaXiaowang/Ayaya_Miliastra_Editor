from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="三维向量加法",
    category="运算节点",
    inputs=[("三维向量1", "三维向量"), ("三维向量2", "三维向量")],
    outputs=[("计算结果", "三维向量")],
    description="计算两个三维向量的加法",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 三维向量加法(三维向量1, 三维向量2):
    """计算两个三维向量的加法"""
    return [三维向量1[0] + 三维向量2[0], 三维向量1[1] + 三维向量2[1], 三维向量1[2] + 三维向量2[2]]
