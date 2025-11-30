from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="更改玩家职业",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家", "实体"), ("职业配置ID", "配置ID")],
    outputs=[("流程出", "流程")],
    description="修改玩家的当前职业为配置ID对应的职业",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 更改玩家职业(game, 目标玩家, 职业配置ID):
    """修改玩家的当前职业为配置ID对应的职业"""
    log_info(f"[更改玩家职业] 执行")
