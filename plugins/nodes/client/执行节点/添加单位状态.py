from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="添加单位状态",
    category="执行节点",
    inputs=[("流程入", "流程"), ("施加目标", "实体"), ("层数", "整数"), ("单位状态配置ID", "配置ID")],
    outputs=[("流程出", "流程")],
    description="为施加目标添加配置ID对应的单位状态",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 添加单位状态(game, 施加目标, 层数, 单位状态配置ID):
    """为施加目标添加配置ID对应的单位状态"""
    log_info(f"[添加单位状态] {施加目标} + 状态#{单位状态配置ID} x{层数}")
