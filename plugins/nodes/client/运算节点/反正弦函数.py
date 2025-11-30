from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="反正弦函数",
    category="运算节点",
    inputs=[("输入", "浮点数")],
    outputs=[("弧度", "浮点数")],
    description="计算输入的反正弦值，返回为弧度值",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 反正弦函数(game, 输入):
    """计算输入的反正弦值，返回为弧度值"""
    import math
    return math.asin(输入)
