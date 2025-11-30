from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询字典是否包含特定键",
    category="查询节点",
    inputs=[("字典", "泛型"), ("键", "泛型")],
    outputs=[("是否包含", "布尔值")],
    description="查询指定字典是否包含特定的键",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询字典是否包含特定键(game, 字典, 键):
    """查询指定字典是否包含特定的键"""
    if isinstance(字典, dict):
        return 键 in 字典
    return False
