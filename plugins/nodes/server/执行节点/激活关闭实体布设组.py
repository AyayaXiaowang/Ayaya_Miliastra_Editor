from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="激活/关闭实体布设组",
    category="执行节点",
    inputs=[("流程入", "流程"), ("实体布设组索引", "整数"), ("是否激活", "布尔值")],
    outputs=[("流程出", "流程")],
    description="修改实体布设组初始创建开关的状态",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 激活关闭实体布设组(game, 实体布设组索引, 是否激活):
    """修改实体布设组初始创建开关的状态"""
    log_info(f"[激活关闭实体布设组] 执行")
