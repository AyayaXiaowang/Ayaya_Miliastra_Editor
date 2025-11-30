from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改装备词条值",
    category="执行节点",
    inputs=[("流程入", "流程"), ("装备索引", "整数"), ("词条序号", "整数"), ("词条数值", "浮点数")],
    outputs=[("流程出", "流程")],
    description="修改指定装备实例对应词条上的值",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改装备词条值(game, 装备索引, 词条序号, 词条数值):
    """修改指定装备实例对应词条上的值"""
    log_info(f"[修改装备词条值] 执行")
