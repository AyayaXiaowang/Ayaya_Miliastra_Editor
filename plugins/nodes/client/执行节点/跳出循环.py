from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="跳出循环",
    category="执行节点",
    inputs=[("流程入", "流程")],
    outputs=[("流程出", "流程")],
    description="从有限循环中跳出。出引脚需要与节点【有限循环】的【跳出循环】入参相连",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 跳出循环(game, 循环体_callback, 循环完成_callback=None, 跳出循环_callback=None):
    """从有限循环中跳出。出引脚需要与节点【有限循环】的【跳出循环】入参相连"""
    log_info(f"[跳出循环] 执行")
