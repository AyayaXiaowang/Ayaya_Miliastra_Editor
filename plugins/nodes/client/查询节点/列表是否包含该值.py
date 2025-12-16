from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="列表是否包含该值",
    category="查询节点",
    inputs=[("值", "泛型"), ("列表", "泛型列表")],
    outputs=[("结果", "布尔值")],
    description="返回列表中是否包含指定值",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 列表是否包含该值(值, 列表):
    """返回列表中是否包含指定值"""
    if isinstance(列表, list):
        return 值 in 列表
    return False
