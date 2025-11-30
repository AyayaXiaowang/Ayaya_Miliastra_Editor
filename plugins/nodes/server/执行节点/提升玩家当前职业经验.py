from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="提升玩家当前职业经验",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家", "实体"), ("经验值", "整数")],
    outputs=[("流程出", "流程")],
    description="提升玩家当前职业经验，超出最大等级的部分会无效",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 提升玩家当前职业经验(game, 目标玩家, 经验值):
    """提升玩家当前职业经验，超出最大等级的部分会无效"""
    log_info(f"[提升玩家当前职业经验] 执行")
