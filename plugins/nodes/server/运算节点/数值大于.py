from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="数值大于",
    category="运算节点",
    inputs=[("左值", "泛型"), ("右值", "泛型")],
    outputs=[("结果", "布尔值")],
    description="返回左值是否大于右值",
    doc_reference="服务器节点/运算节点/运算节点.md",
    input_generic_constraints={
        "左值": ["整数", "浮点数"],
        "右值": ["整数", "浮点数"],
    },
)
def 数值大于(game, 左值, 右值):
    """返回左值是否大于右值"""
    return 左值 > 右值
