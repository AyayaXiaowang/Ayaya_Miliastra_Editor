from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="创建三维向量",
    category="运算节点",
    inputs=[("X分量", "浮点数"), ("Y分量", "浮点数"), ("Z分量", "浮点数")],
    outputs=[("三维向量", "三维向量")],
    description="根据x、y、z分量创建一个三维向量",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 创建三维向量(game, X分量, Y分量, Z分量):
    """根据x、y、z分量创建一个三维向量"""
    return [X分量, Y分量, Z分量]
