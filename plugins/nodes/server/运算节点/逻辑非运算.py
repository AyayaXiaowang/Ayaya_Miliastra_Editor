from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="逻辑非运算",
    category="运算节点",
    inputs=[("输入", "布尔值")],
    outputs=[("结果", "布尔值")],
    description="对输入的布尔值进行非运算后输出",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 逻辑非运算(game, 输入):
    """对输入的布尔值进行非运算后输出"""
    return not 输入
