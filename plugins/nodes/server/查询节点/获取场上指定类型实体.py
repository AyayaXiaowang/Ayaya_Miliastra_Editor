from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取场上指定类型实体",
    category="查询节点",
    inputs=[("实体类型", "枚举")],
    outputs=[("实体列表", "实体列表")],
    description="获取当前场上指定类型的所有实体，该实体列表的数量可能会较大",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取场上指定类型实体(game, 实体类型):
    """获取当前场上指定类型的所有实体，该实体列表的数量可能会较大"""
    return None  # 实体列表
