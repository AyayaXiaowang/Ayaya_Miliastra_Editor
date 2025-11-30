from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="随机卡牌选择器选择列表",
    category="执行节点",
    inputs=[("流程入", "流程"), ("列表", "整数列表")],
    outputs=[("流程出", "流程")],
    description="将输入的列表进行随机排序",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 随机卡牌选择器选择列表(game, 列表):
    """将输入的列表进行随机排序"""
    log_info(f"[随机卡牌选择器选择列表] 执行")
