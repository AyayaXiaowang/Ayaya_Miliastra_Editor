from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="按位异或",
    category="运算节点",
    inputs=[("值1", "整数"), ("值2", "整数")],
    outputs=[("结果", "整数")],
    description="将输入的两个值作为二进制进行按位异或运算后返回结果",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 按位异或(game, 值1, 值2):
    """将输入的两个值作为二进制进行按位异或运算后返回结果"""
    return 值1 ^ 值2
