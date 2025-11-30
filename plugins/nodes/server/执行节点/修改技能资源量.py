from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改技能资源量",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("技能资源配置ID", "配置ID"), ("变更值", "浮点数")],
    outputs=[("流程出", "流程")],
    description="修改技能的资源量，会在当前值上加上变更值，变更值可以为负数",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改技能资源量(game, 目标实体, 技能资源配置ID, 变更值):
    """修改技能的资源量，会在当前值上加上变更值，变更值可以为负数"""
    log_info(f"[修改技能资源量] 执行")
