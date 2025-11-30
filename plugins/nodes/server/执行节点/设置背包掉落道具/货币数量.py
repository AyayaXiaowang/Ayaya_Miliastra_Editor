from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置背包掉落道具/货币数量",
    category="执行节点",
    inputs=[("流程入", "流程"), ("背包持有者实体", "实体"), ("道具/货币配置ID", "配置ID"), ("掉落数量", "整数"), ("掉落类型", "枚举")],
    outputs=[("流程出", "流程")],
    description="设置背包掉落道具/货币的类型和数量",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置背包掉落道具货币数量(game, 背包持有者实体, 道具货币配置ID, 掉落数量, 掉落类型):
    """设置背包掉落道具/货币的类型和数量"""
    log_info(f"[设置背包掉落道具/货币数量] 执行")
