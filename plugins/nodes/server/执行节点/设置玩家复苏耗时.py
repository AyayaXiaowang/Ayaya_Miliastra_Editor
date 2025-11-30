from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置玩家复苏耗时",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("时长", "整数")],
    outputs=[("流程出", "流程")],
    description="设置指定玩家的下一次复苏的时长。如果玩家当前正处于复苏中，不会影响该次复苏的耗时",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置玩家复苏耗时(game, 玩家实体, 时长):
    """设置指定玩家的下一次复苏的时长。如果玩家当前正处于复苏中，不会影响该次复苏的耗时"""
    log_info(f"[设置复苏耗时] {玩家实体} 下次复苏耗时={时长}秒")
