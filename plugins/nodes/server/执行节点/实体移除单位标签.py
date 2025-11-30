from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="实体移除单位标签",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("单位标签索引", "整数")],
    outputs=[("流程出", "流程")],
    description="对指定实体移除单位标签",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 实体移除单位标签(game, 目标实体, 单位标签索引):
    """对指定实体移除单位标签"""
    log_info(f"[实体移除单位标签] 执行")
