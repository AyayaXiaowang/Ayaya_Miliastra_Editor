from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="清除列表",
    category="执行节点",
    inputs=[("流程入", "流程"), ("列表", "泛型列表")],
    outputs=[("流程出", "流程")],
    description="清空指定列表",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 清除列表(game, 列表):
    """清空指定列表"""
    if isinstance(列表, list):
        列表.clear()
        log_info(f"[清除列表] 已清空")
