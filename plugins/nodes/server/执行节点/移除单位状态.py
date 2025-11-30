from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="移除单位状态",
    category="执行节点",
    inputs=[("流程入", "流程"), ("移除目标实体", "实体"), ("单位状态配置ID", "配置ID"), ("移除方式", "枚举"), ("移除者实体", "实体")],
    outputs=[("流程出", "流程")],
    description="从目标实体上移除指定单位状态。可以选择全部移除，或移除其中一层",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 移除单位状态(game, 移除目标实体, 单位状态配置ID, 移除方式, 移除者实体):
    """从目标实体上移除指定单位状态。可以选择全部移除，或移除其中一层"""
    log_info(f"[移除单位状态] 执行")
