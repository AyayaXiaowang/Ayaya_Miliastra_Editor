from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改玩家频道权限",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家GUID", "GUID"), ("频道索引", "整数"), ("是否加入", "布尔值")],
    outputs=[("流程出", "流程")],
    description="修改玩家频道权限",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改玩家频道权限(game, 玩家GUID, 频道索引, 是否加入):
    """修改玩家频道权限"""
    log_info(f"[修改玩家频道权限] 执行")
