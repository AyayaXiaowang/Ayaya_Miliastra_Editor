from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="关闭卡牌选择器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家", "实体"), ("卡牌选择器索引", "整数")],
    outputs=[("流程出", "流程")],
    description="关闭指定玩家当前生效的卡牌选择器",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 关闭卡牌选择器(game, 目标玩家, 卡牌选择器索引):
    """关闭指定玩家当前生效的卡牌选择器"""
    log_info(f"[关闭卡牌选择器] 执行")
