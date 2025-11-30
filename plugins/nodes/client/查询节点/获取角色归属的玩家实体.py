from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取角色归属的玩家实体",
    category="查询节点",
    inputs=[("角色实体", "实体")],
    outputs=[("所属玩家实体", "实体")],
    description="获取角色实体所归属的玩家实体",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取角色归属的玩家实体(game, 角色实体):
    """获取角色实体所归属的玩家实体"""
    return None  # 所属玩家实体
