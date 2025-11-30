from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取在场玩家实体列表",
    category="查询节点",
    outputs=[("玩家实体列表", "实体列表")],
    description="获取在场所有玩家实体组成的列表",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取在场玩家实体列表():
    """获取在场所有玩家实体组成的列表"""
    return None  # 玩家实体列表
