from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置玩家结算计分板展示数据",
    category="执行节点",
    inputs=[("流程入", "流程"), ("设置实体", "实体"), ("数据顺序", "整数"), ("数据名称", "字符串"), ("数据值", "泛型")],
    outputs=[("流程出", "流程")],
    description="设置玩家结算计分板展示数据，显示在关卡结算后弹出的计分板内",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置玩家结算计分板展示数据(game, 设置实体, 数据顺序, 数据名称, 数据值):
    """设置玩家结算计分板展示数据，显示在关卡结算后弹出的计分板内"""
    log_info(f"[设置玩家结算计分板展示数据] 执行")
