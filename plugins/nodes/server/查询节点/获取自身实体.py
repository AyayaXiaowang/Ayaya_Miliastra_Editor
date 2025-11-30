from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取自身实体",
    category="查询节点",
    outputs=[("自身实体", "实体")],
    description="返回该节点图所关联的实体",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取自身实体(game):
    """返回该节点图所关联的实体"""
    return game.get_entity("self")
