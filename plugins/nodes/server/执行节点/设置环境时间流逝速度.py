from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置环境时间流逝速度",
    category="执行节点",
    inputs=[("流程入", "流程"), ("环境时间流逝速度", "浮点数")],
    outputs=[("流程出", "流程")],
    description="每秒流逝分钟数，会被限制在0~60之间（提瓦特速度为24）",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置环境时间流逝速度(game, 环境时间流逝速度):
    """每秒流逝分钟数，会被限制在0~60之间（提瓦特速度为24）"""
    log_info(f"[设置环境时间流逝速度] 执行")
