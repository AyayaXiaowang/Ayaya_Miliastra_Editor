from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="调整玩家背景音乐音量",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("音量", "整数")],
    outputs=[("流程出", "流程")],
    description="调整玩家背景音乐音量",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 调整玩家背景音乐音量(game, 目标实体, 音量):
    """调整玩家背景音乐音量"""
    log_info(f"[调整玩家背景音乐音量] 执行")
