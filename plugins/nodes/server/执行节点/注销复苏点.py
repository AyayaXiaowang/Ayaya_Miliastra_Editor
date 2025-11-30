from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="注销复苏点",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("复苏点序号", "整数")],
    outputs=[("流程出", "流程")],
    description="为该玩家注销指定序号的复苏点。该玩家下次复苏时不会从该复苏点复苏",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 注销复苏点(game, 玩家实体, 复苏点序号):
    """为该玩家注销指定序号的复苏点。该玩家下次复苏时不会从该复苏点复苏"""
    log_info(f"[注销复苏点] 执行")
