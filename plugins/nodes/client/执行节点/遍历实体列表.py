from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="遍历实体列表",
    category="执行节点",
    inputs=[("流程入", "流程"), ("实体列表", "实体列表")],
    outputs=[("流程出", "流程"), ("当前实体", "实体")],
    description="遍历输入实体列表中的每个实体",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 遍历实体列表(game, 实体列表):
    """遍历输入实体列表中的每个实体"""
    return None  # 当前实体
