from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="玩家转向",
    category="执行节点",
    inputs=[("流程入", "流程"), ("转向模式", "枚举")],
    outputs=[("流程出", "流程")],
    description="可以让玩家按照配置的转向模式转向",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 玩家转向(game, 转向模式):
    """可以让玩家按照配置的转向模式转向"""
    log_info(f"[玩家转向] 执行")
