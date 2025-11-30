from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置预设状态",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("预设状态索引", "整数"), ("预设状态值", "整数")],
    outputs=[("流程出", "流程")],
    description="设置指定目标实体的预设状态",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置预设状态(game, 目标实体, 预设状态索引, 预设状态值):
    """设置指定目标实体的预设状态"""
    log_info(f"[设置预设状态] {目标实体} 预设状态[{预设状态索引}] = {预设状态值}")
