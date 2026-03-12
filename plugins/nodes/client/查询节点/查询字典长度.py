from __future__ import annotations

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *  # noqa: F401,F403


@node_spec(
    name="查询字典长度",
    category="查询节点",
    inputs=[("字典", "泛型字典")],
    outputs=[("长度", "整数")],
    description="查询字典中键值对的数量",
    doc_reference="客户端节点/查询节点/查询节点.md",
)
def 查询字典长度(game, 字典):
    """查询字典中键值对的数量。"""
    return len(字典)

