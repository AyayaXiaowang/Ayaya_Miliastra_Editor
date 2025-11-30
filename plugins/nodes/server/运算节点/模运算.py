from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="模运算",
    category="运算节点",
    inputs=[("被模数", "整数"), ("模数", "整数")],
    outputs=[("结果", "整数")],
    description="返回输入2对输入1的取模运算",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 模运算(game, 被模数, 模数):
    """返回输入2对输入1的取模运算"""
    return 被模数 % 模数
