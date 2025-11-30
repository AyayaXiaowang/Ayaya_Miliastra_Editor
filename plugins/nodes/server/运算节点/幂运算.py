from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="幂运算",
    category="运算节点",
    inputs=[("底数", "泛型"), ("指数", "泛型")],
    outputs=[("结果", "泛型")],
    description="计算底数的指数次幂",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 幂运算(game, 底数, 指数):
    """计算底数的指数次幂"""
    return 底数 ** 指数
