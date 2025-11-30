from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="移除单位状态",
    category="执行节点",
    inputs=[("流程入", "流程"), ("移除目标", "实体"), ("单位状态配置ID", "配置ID")],
    outputs=[("流程出", "流程")],
    description="移除目标实体上指定配置ID对应的单位状态",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 移除单位状态(game, 移除目标, 单位状态配置ID):
    """移除目标实体上指定配置ID对应的单位状态"""
    log_info(f"[移除单位状态] {移除目标} - 状态#{单位状态配置ID}")
