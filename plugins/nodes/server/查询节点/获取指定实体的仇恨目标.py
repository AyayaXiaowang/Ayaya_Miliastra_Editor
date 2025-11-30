from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取指定实体的仇恨目标",
    category="查询节点",
    inputs=[("仇恨拥有者", "实体")],
    outputs=[("仇恨目标", "实体")],
    description="获取指定实体的仇恨目标",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取指定实体的仇恨目标(game, 仇恨拥有者):
    """获取指定实体的仇恨目标"""
    return game.create_mock_entity("仇恨目标")
