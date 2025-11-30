from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="定点位移",
    category="执行节点",
    inputs=[("流程入", "流程"), ("位移时长", "浮点数"), ("位移衰减时长", "浮点数"), ("位移速度", "浮点数"), ("位移目标位置", "三维向量"), ("碰撞是否终止位移", "布尔值")],
    outputs=[("流程出", "流程")],
    description="定点位移，从当前位置向目标位置位移 可配置位移时长与位移速度，当这二者都比较小时，可能无法位移到目标位置",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 定点位移(game, 位移时长, 位移衰减时长, 位移速度, 位移目标位置, 碰撞是否终止位移):
    """定点位移，从当前位置向目标位置位移 可配置位移时长与位移速度，当这二者都比较小时，可能无法位移到目标位置"""
    log_info(f"[定点位移] 执行")
