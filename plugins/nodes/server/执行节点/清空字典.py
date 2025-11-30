from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="清空字典",
    category="执行节点",
    inputs=[("流程入", "流程"), ("字典", "泛型")],
    outputs=[("流程出", "流程")],
    description="清空指定字典的键值对",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 清空字典(game, 字典):
    """清空指定字典的键值对"""
    log_info(f"[清空字典] 执行")
