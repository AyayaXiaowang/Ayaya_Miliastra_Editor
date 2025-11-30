from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取指定玩家所有角色实体",
    category="查询节点",
    inputs=[("玩家实体", "实体")],
    outputs=[("角色实体列表", "实体列表")],
    description="获取指定玩家实体的所有角色实体列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取指定玩家所有角色实体(game, 玩家实体):
    """获取指定玩家实体的所有角色实体列表"""
    return [game.create_mock_entity("角色1")]
