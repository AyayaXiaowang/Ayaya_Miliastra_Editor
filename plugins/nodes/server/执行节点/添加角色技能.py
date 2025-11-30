from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="添加角色技能",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("技能配置ID", "配置ID"), ("技能槽位", "枚举")],
    outputs=[("流程出", "流程")],
    description="为指定目标角色的某个技能槽位添加技能",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 添加角色技能(game, 目标实体, 技能配置ID, 技能槽位):
    """为指定目标角色的某个技能槽位添加技能"""
    log_info(f"[添加角色技能] 执行")
