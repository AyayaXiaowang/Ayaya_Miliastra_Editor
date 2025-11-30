from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="除法运算",
    category="运算节点",
    inputs=[("左值", "泛型"), ("右值", "泛型")],
    outputs=[("结果", "泛型")],
    description="除法运算，支持浮点数除法和整数除法。整数除法返回整除结果 除数不应为0，否则可能返回非法值",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 除法运算(game, 左值, 右值):
    """除法运算，支持浮点数除法和整数除法。整数除法返回整除结果 除数不应为0，否则可能返回非法值"""
    if isinstance(左值, int) and isinstance(右值, int):
        return 左值 // 右值  # 整数除法
    return 左值 / 右值  # 浮点数除法
