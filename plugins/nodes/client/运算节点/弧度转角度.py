from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="弧度转角度",
    category="运算节点",
    inputs=[("弧度", "浮点数")],
    outputs=[("角度", "浮点数")],
    description="将弧度值转为角度值",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 弧度转角度(game, 弧度):
    """将弧度值转为角度值"""
    import math
    return math.degrees(弧度)
