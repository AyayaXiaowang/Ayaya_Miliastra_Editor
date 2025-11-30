from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询玩家职业",
    category="查询节点",
    inputs=[("玩家实体", "实体")],
    outputs=[("职业配置ID", "配置ID")],
    description="查询玩家当前的职业，会输出该职业的配置ID",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询玩家职业(game, 玩家实体):
    """查询玩家当前的职业，会输出该职业的配置ID"""
    return "职业ID_战士"
