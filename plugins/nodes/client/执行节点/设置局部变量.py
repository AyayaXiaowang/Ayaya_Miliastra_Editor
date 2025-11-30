from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置局部变量",
    category="执行节点",
    inputs=[("流程入", "流程"), ("变量名", "字符串"), ("变量值", "泛型")],
    outputs=[("流程出", "流程")],
    description="设置局部变量的值",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 设置局部变量(game, 变量名, 变量值):
    """设置局部变量的值"""
    log_info(f"[局部变量] {变量名} = {变量值}")
