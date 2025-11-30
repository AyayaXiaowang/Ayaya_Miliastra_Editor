from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取以目标为仇恨目标的拥有者列表",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("仇恨拥有者列表", "实体列表")],
    description="查询哪些实体以目标实体为仇恨目标",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取以目标为仇恨目标的拥有者列表(game, 目标实体):
    """查询哪些实体以目标实体为仇恨目标"""
    return [game.create_mock_entity("仇恨者1")]
