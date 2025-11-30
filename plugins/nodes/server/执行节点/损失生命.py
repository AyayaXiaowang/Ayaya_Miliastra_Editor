from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="损失生命",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("生命损失量", "浮点数"), ("是否致命", "布尔值"), ("是否可被无敌抵挡", "布尔值"), ("是否可被锁定生命值抵挡", "布尔值"), ("伤害跳字类型", "枚举")],
    outputs=[("流程出", "流程")],
    description="使指定目标直接损失生命。损失生命不是攻击，因此不会触发攻击相关的事件",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 损失生命(game, 目标实体, 生命损失量, 是否致命, 是否可被无敌抵挡, 是否可被锁定生命值抵挡, 伤害跳字类型):
    """使指定目标直接损失生命。损失生命不是攻击，因此不会触发攻击相关的事件"""
    log_info(f"[损失生命] 执行")
