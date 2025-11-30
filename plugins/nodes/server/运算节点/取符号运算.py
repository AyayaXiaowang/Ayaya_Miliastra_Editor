from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="取符号运算",
    category="运算节点",
    inputs=[("输入", "泛型")],
    outputs=[("结果", "泛型")],
    description="输入为正数时，返回1 输入为负数时，返回-1 输入为0时，返回0",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 取符号运算(game, 输入):
    """输入为正数时，返回1 输入为负数时，返回-1 输入为0时，返回0"""
    if 输入 > 0:
        return 1
    elif 输入 < 0:
        return -1
    return 0
