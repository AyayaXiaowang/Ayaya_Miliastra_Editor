from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置玩家逃跑合法性",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("是否合法", "布尔值")],
    outputs=[("流程出", "流程")],
    description="设置指定玩家逃跑的合法性",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置玩家逃跑合法性(game, 玩家实体, 是否合法):
    """设置指定玩家逃跑的合法性"""
    log_info(f"[设置玩家逃跑合法性] 执行")
