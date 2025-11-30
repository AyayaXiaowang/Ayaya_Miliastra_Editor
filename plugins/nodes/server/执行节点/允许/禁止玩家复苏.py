from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="允许/禁止玩家复苏",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("是否允许", "布尔值")],
    outputs=[("流程出", "流程")],
    description="设置指定玩家是否允许复苏",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 允许或禁止玩家复苏(game, 玩家实体, 是否允许):
    """设置指定玩家是否允许复苏"""
    log_info(f"[允许或禁止玩家复苏] 执行")
