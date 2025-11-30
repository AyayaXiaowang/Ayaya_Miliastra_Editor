from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="取较大值",
    category="运算节点",
    inputs=[("输入1", "泛型"), ("输入2", "泛型")],
    outputs=[("较大值", "泛型")],
    description="取出两个输入中较大的一个",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 取较大值(game, 输入1, 输入2):
    """取出两个输入中较大的一个"""
    return max(输入1, 输入2)
