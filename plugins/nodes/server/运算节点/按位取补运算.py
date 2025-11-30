from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="按位取补运算",
    category="运算节点",
    inputs=[("值", "整数")],
    outputs=[("结果", "整数")],
    description="将输入值作为二进制进行按位取补运算后返回结果",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 按位取补运算(game, 值):
    """将输入值作为二进制进行按位取补运算后返回结果"""
    return ~值
