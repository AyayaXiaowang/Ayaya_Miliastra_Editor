from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="角度转弧度",
    category="运算节点",
    inputs=[("角度值", "浮点数")],
    outputs=[("弧度值", "浮点数")],
    description="将角度值转为弧度值",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 角度转弧度(game, 角度值):
    """将角度值转为弧度值"""
    return math.radians(角度值)
