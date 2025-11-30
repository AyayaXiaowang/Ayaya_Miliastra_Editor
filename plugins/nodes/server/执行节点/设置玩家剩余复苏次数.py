from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置玩家剩余复苏次数",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("剩余次数", "整数")],
    outputs=[("流程出", "流程")],
    description="设置指定玩家剩余复苏次数。设置为0时，该玩家无法复苏",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置玩家剩余复苏次数(game, 玩家实体, 剩余次数):
    """设置指定玩家剩余复苏次数。设置为0时，该玩家无法复苏"""
    log_info(f"[设置复苏次数] {玩家实体} 剩余次数={剩余次数}")
