from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询玩家角色是否全部倒下",
    category="查询节点",
    inputs=[("玩家实体", "实体")],
    outputs=[("结果", "布尔值")],
    description="查询玩家的所有角色是否已全部倒下",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询玩家角色是否全部倒下(game, 玩家实体):
    """查询玩家的所有角色是否已全部倒下"""
    return False
