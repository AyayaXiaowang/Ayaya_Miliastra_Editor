from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="加法运算",
    category="运算节点",
    inputs=[("左值", "泛型"), ("右值", "泛型")],
    outputs=[("结果", "泛型")],
    description="计算两个浮点数或整数的加法",
    doc_reference="客户端节点/运算节点/运算节点.md",
    input_generic_constraints={
        "左值": ["整数", "浮点数"],
        "右值": ["整数", "浮点数"],
    },
    output_generic_constraints={
        "结果": ["整数", "浮点数"],
    },
)
def 加法运算(game, 左值, 右值):
    """计算两个浮点数或整数的加法"""
    return 左值 + 右值
