from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="重置技能目标",
    category="执行节点",
    inputs=[("流程入", "流程")],
    outputs=[("流程出", "流程")],
    description="重置技能目标，重新运行一次技能选取逻辑，选择一个新的目标",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 重置技能目标(game):
    """重置技能目标，重新运行一次技能选取逻辑，选择一个新的目标"""
    log_info(f"[重置技能目标] 执行")
