from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="击倒玩家所有角色",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体")],
    outputs=[("流程出", "流程")],
    description="击倒指定玩家的所有角色，会导致该玩家进入玩家所有角色倒下状态",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 击倒玩家所有角色(game, 玩家实体):
    """击倒指定玩家的所有角色，会导致该玩家进入玩家所有角色倒下状态"""
    log_info(f"[击倒角色] {玩家实体} 所有角色倒下")
