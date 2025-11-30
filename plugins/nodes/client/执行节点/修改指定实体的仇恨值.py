from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改指定实体的仇恨值",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("仇恨拥有者实体", "实体"), ("仇恨值增量", "整数")],
    outputs=[("流程出", "流程")],
    description="仅自定义仇恨模式可用 修改指定实体在仇恨拥有者实体上的仇恨值",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 修改指定实体的仇恨值(game, 目标实体, 仇恨拥有者实体, 仇恨值增量):
    """仅自定义仇恨模式可用 修改指定实体在仇恨拥有者实体上的仇恨值"""
    log_info(f"[修改指定实体的仇恨值] 执行")
