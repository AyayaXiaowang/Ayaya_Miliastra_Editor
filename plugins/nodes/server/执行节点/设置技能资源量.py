from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置技能资源量",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("技能资源配置ID", "配置ID"), ("目标值", "浮点数")],
    outputs=[("流程出", "流程")],
    description="修改角色的技能资源量",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置技能资源量(game, 目标实体, 技能资源配置ID, 目标值):
    """修改角色的技能资源量"""
    log_info(f"[设置技能资源量] 执行")
