from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置玩家结算排名数值",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("排名数值", "整数")],
    outputs=[("流程出", "流程")],
    description="设置玩家结算后的排名数值，再按照【关卡设置】-【结算】中的【排名数值比较顺序】的设置来决定最终的排名顺序",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置玩家结算排名数值(game, 玩家实体, 排名数值):
    """设置玩家结算后的排名数值，再按照【关卡设置】-【结算】中的【排名数值比较顺序】的设置来决定最终的排名顺序"""
    log_info(f"[设置玩家结算排名数值] 执行")
