from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="乘法运算",
    category="运算节点",
    outputs=[("结果", "泛型")],
    description="乘法运算，支持浮点数乘法和整数乘法",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 乘法运算():
    """乘法运算，支持浮点数乘法和整数乘法"""
    # 注意：参数在节点定义中缺失，这里返回Mock
    return 0
