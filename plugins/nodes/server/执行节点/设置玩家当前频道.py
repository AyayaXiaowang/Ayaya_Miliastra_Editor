from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置玩家当前频道",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家GUID", "GUID"), ("频道索引列表", "整数列表")],
    outputs=[("流程出", "流程")],
    description="设置玩家当前可用的频道，在列表中的频道该玩家可用，不在的该玩家不可用",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置玩家当前频道(game, 玩家GUID, 频道索引列表):
    """设置玩家当前可用的频道，在列表中的频道该玩家可用，不在的该玩家不可用"""
    log_info(f"[设置玩家当前频道] 执行")
