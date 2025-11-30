from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="恢复生命值",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("恢复量", "浮点数"), ("是否忽略恢复调整效果", "布尔值"), ("本次治疗的仇恨倍率", "浮点数"), ("本次治疗的仇恨增量", "整数")],
    outputs=[("流程出", "流程")],
    description="为目标实体发起一次恢复生命值",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 恢复生命值(game, 目标实体, 恢复量, 是否忽略恢复调整效果, 本次治疗的仇恨倍率, 本次治疗的仇恨增量):
    """为目标实体发起一次恢复生命值"""
    log_info(f"[恢复生命值] 执行")
