from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="以槽位删除角色技能",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("角色技能槽位", "枚举")],
    outputs=[("流程出", "流程")],
    description="删除目标角色指定槽位的技能",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 以槽位删除角色技能(game, 目标实体, 角色技能槽位):
    """删除目标角色指定槽位的技能"""
    log_info(f"[以槽位删除角色技能] 执行")
