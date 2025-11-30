from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="初始化角色技能",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("角色技能槽位", "枚举")],
    outputs=[("流程出", "流程")],
    description="使目标角色的技能重置为职业模板上配置的技能",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 初始化角色技能(game, 目标实体, 角色技能槽位):
    """使目标角色的技能重置为职业模板上配置的技能"""
    log_info(f"[初始化角色技能] 执行")
