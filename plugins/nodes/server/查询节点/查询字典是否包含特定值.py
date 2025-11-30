from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询字典是否包含特定值",
    category="查询节点",
    inputs=[("字典", "泛型"), ("值", "泛型")],
    outputs=[("是否包含", "布尔值")],
    description="查询指定字典是否包含特定的值",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询字典是否包含特定值(game, 字典, 值):
    """查询指定字典是否包含特定的值"""
    if isinstance(字典, dict):
        return 值 in 字典.values()
    return False
