from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="消耗礼盒",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("礼盒索引", "整数"), ("消耗数量", "整数")],
    outputs=[("流程出", "流程")],
    description="可以消耗指定玩家的奇遇礼盒",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 消耗礼盒(game, 玩家实体, 礼盒索引, 消耗数量):
    """可以消耗指定玩家的奇遇礼盒"""
    log_info(f"[消耗礼盒] 执行")
