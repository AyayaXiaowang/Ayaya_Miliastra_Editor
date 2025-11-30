from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取字典中值组成的列表",
    category="查询节点",
    inputs=[("字典", "泛型")],
    outputs=[("值列表", "泛型列表")],
    description="获取字典中所有值组成的列表。由于字典中键值对是无序排列的，所以取出的值列表也不一定按照其插入顺序排列",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取字典中值组成的列表(game, 字典):
    """获取字典中所有值组成的列表。由于字典中键值对是无序排列的，所以取出的值列表也不一定按照其插入顺序排列"""
    if isinstance(字典, dict):
        return list(字典.values())
    return []
