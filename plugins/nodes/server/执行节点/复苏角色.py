from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="复苏角色",
    category="执行节点",
    inputs=[("流程入", "流程"), ("角色实体", "实体")],
    outputs=[("流程出", "流程")],
    description="复苏指定的角色实体",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 复苏角色(game, 角色实体):
    """复苏指定的角色实体"""
    log_info(f"[复苏角色] 执行")
