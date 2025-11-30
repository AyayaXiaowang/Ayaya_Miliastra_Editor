from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取目标所在仇恨列表的拥有者列表",
    category="查询节点",
    inputs=[("查询目标", "实体")],
    outputs=[("仇恨拥有者列表", "实体列表")],
    description="查询指定目标实体在哪些实体的仇恨列表中",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取目标所在仇恨列表的拥有者列表(game, 查询目标):
    """查询指定目标实体在哪些实体的仇恨列表中"""
    return [game.create_mock_entity("仇恨者1"), game.create_mock_entity("仇恨者2")]
