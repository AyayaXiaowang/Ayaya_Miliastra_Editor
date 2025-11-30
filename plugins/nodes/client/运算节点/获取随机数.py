from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取随机数",
    category="运算节点",
    inputs=[("下限", "泛型"), ("上限", "泛型")],
    outputs=[("随机数", "泛型")],
    description="获取一个大于等于下限，小于等于上限的随机数。注意该节点生成的随机数包含上下限",
    doc_reference="客户端节点/运算节点/运算节点.md"
)
def 获取随机数(下限, 上限):
    """获取一个大于等于下限，小于等于上限的随机数。注意该节点生成的随机数包含上下限"""
    result = random.uniform(下限, 上限)
    log_info(f"[随机数] {下限}-{上限} -> {result:.2f}")
    return result
