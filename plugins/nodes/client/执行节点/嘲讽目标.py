from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="嘲讽目标",
    category="执行节点",
    inputs=[("流程入", "流程"), ("嘲讽者实体", "实体"), ("目标实体", "实体")],
    outputs=[("流程出", "流程")],
    description="仅自定义仇恨模式可用 嘲讽者实体嘲讽指定目标实体",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 嘲讽目标(game, 嘲讽者实体, 目标实体):
    """仅自定义仇恨模式可用 嘲讽者实体嘲讽指定目标实体"""
    log_info(f"[嘲讽目标] 执行")
