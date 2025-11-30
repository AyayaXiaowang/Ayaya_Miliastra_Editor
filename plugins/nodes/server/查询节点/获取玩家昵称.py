from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取玩家昵称",
    category="查询节点",
    inputs=[("玩家实体", "实体")],
    outputs=[("玩家昵称", "字符串")],
    description="获取玩家的昵称",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取玩家昵称(game, 玩家实体):
    """获取玩家的昵称"""
    return "玩家昵称"
