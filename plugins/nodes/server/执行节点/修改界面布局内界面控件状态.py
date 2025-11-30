from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改界面布局内界面控件状态",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家", "实体"), ("界面控件索引", "整数"), ("显示状态", "枚举")],
    outputs=[("流程出", "流程")],
    description="通过界面控件索引来修改目标玩家界面布局内对应界面控件的状态",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改界面布局内界面控件状态(game, 目标玩家, 界面控件索引, 显示状态):
    """通过界面控件索引来修改目标玩家界面布局内对应界面控件的状态"""
    log_info(f"[修改界面布局内界面控件状态] 执行")
