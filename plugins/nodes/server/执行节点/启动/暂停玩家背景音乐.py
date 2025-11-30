from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="启动/暂停玩家背景音乐",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("是否恢复", "布尔值")],
    outputs=[("流程出", "流程")],
    description="修改对应玩家的背景音乐状态",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 启动或暂停玩家背景音乐(game, 目标实体, 是否恢复):
    """修改对应玩家的背景音乐状态"""
    log_info(f"[启动或暂停玩家背景音乐] 执行")
