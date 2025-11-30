from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="绝对值运算",
    category="运算节点",
    inputs=[("输入", "泛型")],
    outputs=[("结果", "泛型")],
    description="返回输入的绝对值",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 绝对值运算(game, 输入):
    """返回输入的绝对值"""
    return abs(输入)
