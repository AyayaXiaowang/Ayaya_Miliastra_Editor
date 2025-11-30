from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="移除装备词条",
    category="执行节点",
    inputs=[("流程入", "流程"), ("装备索引", "整数"), ("词条序号", "整数")],
    outputs=[("流程出", "流程")],
    description="移除指定装备实例的对应词条",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 移除装备词条(game, 装备索引, 词条序号):
    """移除指定装备实例的对应词条"""
    log_info(f"[移除装备词条] 执行")
