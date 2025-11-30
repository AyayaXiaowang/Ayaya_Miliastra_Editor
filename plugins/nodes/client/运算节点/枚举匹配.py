from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="枚举匹配",
    category="运算节点",
    inputs=[("枚举1", "泛型"), ("枚举2", "泛型")],
    outputs=[("结果", "布尔值")],
    description="确认枚举的类型后，判断两个输入的值是否相等",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 枚举匹配(game, 枚举1, 枚举2):
    """确认枚举的类型后，判断两个输入的值是否相等"""
    return 枚举1 == 枚举2
