from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置角色技能冷却",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("角色技能槽位", "枚举"), ("冷却剩余时间", "浮点数"), ("是否限制最大冷却时间", "布尔值")],
    outputs=[("流程出", "流程")],
    description="直接设置目标角色某个技能槽位的冷却为指定值",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置角色技能冷却(game, 目标实体, 角色技能槽位, 冷却剩余时间, 是否限制最大冷却时间):
    """直接设置目标角色某个技能槽位的冷却为指定值"""
    log_info(f"[设置角色技能冷却] 执行")
