from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取指定玩家的角色实体",
    category="查询节点",
    inputs=[("玩家实体", "实体")],
    outputs=[("角色实体", "实体")],
    description="获取指定玩家实体的角色实体",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取指定玩家的角色实体(game, 玩家实体):
    """获取指定玩家实体的角色实体"""
    return None  # 角色实体
