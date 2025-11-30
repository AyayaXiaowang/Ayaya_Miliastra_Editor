from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="强制退出瞄准状态",
    category="执行节点",
    inputs=[("流程入", "流程")],
    outputs=[("流程出", "流程")],
    description="当角色处于瞄准状态是，会强制退出瞄准状态",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 强制退出瞄准状态(game):
    """当角色处于瞄准状态是，会强制退出瞄准状态"""
    log_info(f"[强制退出瞄准状态] 执行")
