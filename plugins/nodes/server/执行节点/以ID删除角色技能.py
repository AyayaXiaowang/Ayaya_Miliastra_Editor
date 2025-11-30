from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="以ID删除角色技能",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("技能配置ID", "配置ID")],
    outputs=[("流程出", "流程")],
    description="遍历角色的所有槽位，删除所有指定配置ID的技能",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 以ID删除角色技能(game, 目标实体, 技能配置ID):
    """遍历角色的所有槽位，删除所有指定配置ID的技能"""
    log_info(f"[以ID删除角色技能] 执行")
