from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取玩家复苏耗时",
    category="查询节点",
    inputs=[("玩家实体", "实体")],
    outputs=[("时长", "整数")],
    description="获取指定玩家实体的复苏耗时，单位秒",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取玩家复苏耗时(game, 玩家实体):
    """获取指定玩家实体的复苏耗时，单位秒"""
    return 5.0
