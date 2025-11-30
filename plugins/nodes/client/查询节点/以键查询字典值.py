from __future__ import annotations

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info


@node_spec(
    name="以键查询字典值",
    category="查询节点",
    inputs=[("字典", "泛型"), ("键", "泛型")],
    outputs=[("值", "泛型")],
    description="根据键查询字典中对应的值，如果键不存在，则返回类型默认值",
    doc_reference="客户端节点/查询节点/查询节点.md",
)
def 以键查询字典值(game, 字典, 键):
    """根据键查询字典中对应的值，如果键不存在，则返回类型默认值"""
    if isinstance(字典, dict):
        return 字典.get(键)
    return None


