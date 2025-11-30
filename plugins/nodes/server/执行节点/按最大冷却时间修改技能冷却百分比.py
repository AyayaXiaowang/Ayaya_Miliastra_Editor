from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="按最大冷却时间修改技能冷却百分比",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("角色技能槽位", "枚举"), ("冷却比例修改值", "浮点数"), ("是否限制最大冷却时间", "布尔值")],
    outputs=[("流程出", "流程")],
    description="通过技能最大冷却时间的百分比来修改角色某个技能槽位内的技能",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 按最大冷却时间修改技能冷却百分比(game, 目标实体, 角色技能槽位, 冷却比例修改值, 是否限制最大冷却时间):
    """通过技能最大冷却时间的百分比来修改角色某个技能槽位内的技能"""
    log_info(f"[按最大冷却时间修改技能冷却百分比] 执行")
