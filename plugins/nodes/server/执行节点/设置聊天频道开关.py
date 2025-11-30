from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置聊天频道开关",
    category="执行节点",
    inputs=[("流程入", "流程"), ("频道索引", "整数"), ("文字开关", "布尔值")],
    outputs=[("流程出", "流程")],
    description="设置聊天频道的开关",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置聊天频道开关(game, 频道索引, 文字开关):
    """设置聊天频道的开关"""
    log_info(f"[设置聊天频道开关] 执行")
