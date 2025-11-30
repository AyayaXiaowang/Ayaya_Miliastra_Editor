from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="转发事件",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体")],
    outputs=[("流程出", "流程")],
    description="向指定目标实体转发此节点所在的执行流的源头事件。被转发的目标实体上的节点图上的同名事件会被触发",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 转发事件(game, 目标实体):
    """向指定目标实体转发此节点所在的执行流的源头事件。被转发的目标实体上的节点图上的同名事件会被触发"""
    log_info(f"[转发事件] -> {目标实体}")
