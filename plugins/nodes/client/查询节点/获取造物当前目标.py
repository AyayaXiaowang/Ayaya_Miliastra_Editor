from __future__ import annotations

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *  # noqa: F401,F403


@node_spec(
    name="获取造物当前目标",
    category="查询节点",
    inputs=[("造物实体", "实体")],
    outputs=[("目标实体", "实体")],
    description="根据造物当前行为的不同，目标实体也不尽相同",
    doc_reference="客户端节点/查询节点/查询节点.md",
)
def 获取造物当前目标(game, 造物实体):
    """获取造物当前目标实体。"""
    return game.create_mock_entity("目标实体")

