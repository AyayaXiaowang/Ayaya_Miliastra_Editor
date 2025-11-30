from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取列表最小值",
    category="查询节点",
    inputs=[("列表", "泛型")],
    outputs=[("最小值", "泛型")],
    description="仅对浮点数列表和整数列表有意义，返回列表中的最小值",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取列表最小值(列表):
    """仅对浮点数列表和整数列表有意义，返回列表中的最小值"""
    if isinstance(列表, list) and len(列表) > 0:
        return min(列表)
    return None
