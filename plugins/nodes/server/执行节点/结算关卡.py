from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="结算关卡",
    category="执行节点",
    inputs=[("流程入", "流程")],
    outputs=[("流程出", "流程")],
    description="触发关卡结算流程，会按照关卡结算内的逻辑进行局外的逻辑结算",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 结算关卡(game):
    """触发关卡结算流程，会按照关卡结算内的逻辑进行局外的逻辑结算"""
    log_info(f"[结算关卡] 开始结算")
