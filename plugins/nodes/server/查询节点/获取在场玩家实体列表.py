from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取在场玩家实体列表",
    category="查询节点",
    outputs=[("玩家实体列表", "实体列表")],
    description="获取在场所有玩家实体组成的列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取在场玩家实体列表(game):
    """获取在场所有玩家实体组成的列表"""
    return [game.create_mock_entity("玩家1"), game.create_mock_entity("玩家2")]
