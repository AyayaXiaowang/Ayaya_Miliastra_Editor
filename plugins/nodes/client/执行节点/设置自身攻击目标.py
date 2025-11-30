from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置自身攻击目标",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("是否立即转向", "布尔值")],
    outputs=[("流程出", "流程")],
    description="将目标实体设置为自身的攻击目标",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 设置自身攻击目标(game, 目标实体, 是否立即转向):
    """将目标实体设置为自身的攻击目标"""
    log_info(f"[设置自身攻击目标] 执行")
