from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="算术平方根运算",
    category="运算节点",
    inputs=[("输入", "浮点数")],
    outputs=[("结果", "浮点数")],
    description="返回输入值的算术平方根",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 算术平方根运算(game, 输入):
    """返回输入值的算术平方根"""
    return math.sqrt(输入)
