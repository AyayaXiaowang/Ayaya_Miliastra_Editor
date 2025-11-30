from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置玩家段位变化分数",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("结算状态", "枚举"), ("变化分数", "整数")],
    outputs=[("流程出", "流程")],
    description="根据结算状态设置玩家的段位变化分数",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置玩家段位变化分数(game, 玩家实体, 结算状态, 变化分数):
    """根据结算状态设置玩家的段位变化分数"""
    log_info(f"[设置玩家段位变化分数] 执行")
