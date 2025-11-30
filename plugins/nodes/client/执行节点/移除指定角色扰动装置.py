from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="移除指定角色扰动装置",
    category="执行节点",
    inputs=[("流程入", "流程"), ("扰动装置类型", "枚举")],
    outputs=[("流程出", "流程")],
    description="移除指定类型的角色扰动装置",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 移除指定角色扰动装置(game, 扰动装置类型):
    """移除指定类型的角色扰动装置"""
    log_info(f"[移除扰动装置] 类型={扰动装置类型}")
