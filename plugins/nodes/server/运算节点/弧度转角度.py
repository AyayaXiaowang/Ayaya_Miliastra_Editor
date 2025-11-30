from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="弧度转角度",
    category="运算节点",
    inputs=[("弧度值", "浮点数")],
    outputs=[("角度值", "浮点数")],
    description="将弧度值转为角度值",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 弧度转角度(game, 弧度值):
    """将弧度值转为角度值"""
    return math.degrees(弧度值)
