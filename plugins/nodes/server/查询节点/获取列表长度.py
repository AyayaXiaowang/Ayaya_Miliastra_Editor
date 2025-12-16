from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取列表长度",
    category="查询节点",
    inputs=[("列表", "泛型列表")],
    outputs=[("长度", "整数")],
    description="获取列表长度（列表中的元素个数）",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取列表长度(列表):
    """获取列表长度（列表中的元素个数）"""
    if isinstance(列表, list):
        return len(列表)
    return 0
