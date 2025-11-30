from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取碰撞触发器内所有实体",
    category="查询节点",
    inputs=[("目标实体", "实体"), ("触发器序号", "整数")],
    outputs=[("实体列表", "实体列表")],
    description="获取目标实体上碰撞触发器组件中特定序号对应的碰撞触发器内的所有实体",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取碰撞触发器内所有实体(game, 目标实体, 触发器序号):
    """获取目标实体上碰撞触发器组件中特定序号对应的碰撞触发器内的所有实体"""
    return [game.create_mock_entity("实体1"), game.create_mock_entity("实体2")]
