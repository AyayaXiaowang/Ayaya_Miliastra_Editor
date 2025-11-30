from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="正切函数",
    category="运算节点",
    inputs=[("弧度", "浮点数")],
    outputs=[("结果", "浮点数")],
    description="计算输入弧度的正切",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 正切函数(game, 弧度):
    """计算输入弧度的正切"""
    return math.tan(弧度)
