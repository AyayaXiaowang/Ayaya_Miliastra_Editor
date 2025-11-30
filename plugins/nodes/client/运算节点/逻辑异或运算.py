from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="逻辑异或运算",
    category="运算节点",
    inputs=[("条件1", "布尔值"), ("条件2", "布尔值")],
    outputs=[("结果", "布尔值")],
    description="对输入的两个布尔值进行异或运算后输出",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 逻辑异或运算(条件1, 条件2):
    """对输入的两个布尔值进行异或运算后输出"""
    return 条件1 != 条件2
