from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询指定实体的仇恨值",
    category="查询节点",
    inputs=[("查询目标", "实体"), ("仇恨拥有者", "实体")],
    outputs=[("仇恨值", "整数")],
    description="查询目标实体在仇恨拥有者上的仇恨值",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询指定实体的仇恨值(game, 查询目标, 仇恨拥有者):
    """查询目标实体在仇恨拥有者上的仇恨值"""
    return 500
