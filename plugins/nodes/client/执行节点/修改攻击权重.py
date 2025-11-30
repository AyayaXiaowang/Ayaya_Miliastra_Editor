from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改攻击权重",
    category="执行节点",
    inputs=[("流程入", "流程"), ("当前攻击目标的权重", "浮点数"), ("是否强制选一次目标", "布尔值")],
    outputs=[("流程出", "流程")],
    description="可以修改当前攻击目标的权重",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 修改攻击权重(game, 当前攻击目标的权重, 是否强制选一次目标):
    """可以修改当前攻击目标的权重"""
    log_info(f"[修改攻击权重] 执行")
