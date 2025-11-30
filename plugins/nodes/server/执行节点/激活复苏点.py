from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="激活复苏点",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("复苏点序号", "整数")],
    outputs=[("流程出", "流程")],
    description="为该玩家激活指定序号的复苏点，此玩家后续触发复苏逻辑时，可以从该复苏点复苏",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 激活复苏点(game, 玩家实体, 复苏点序号):
    """为该玩家激活指定序号的复苏点，此玩家后续触发复苏逻辑时，可以从该复苏点复苏"""
    log_info(f"[激活复苏点] 执行")
