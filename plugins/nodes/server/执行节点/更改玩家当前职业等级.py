from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="更改玩家当前职业等级",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家", "实体"), ("等级", "整数")],
    outputs=[("流程出", "流程")],
    description="修改玩家当前职业等级，若超出定义的等级范围则会失效",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 更改玩家当前职业等级(game, 目标玩家, 等级):
    """修改玩家当前职业等级，若超出定义的等级范围则会失效"""
    log_info(f"[更改玩家当前职业等级] 执行")
