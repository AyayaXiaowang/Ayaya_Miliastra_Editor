from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="玩家所有角色倒下时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("玩家实体", "实体"), ("原因", "枚举")],
    description="玩家的所有角色实体均倒下时，玩家实体的节点图上触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md",
    output_enum_options={
        "原因": [
            "倒下原因_节点图导致",
            "倒下原因_正常被击倒",
            "倒下原因_非正常被击倒",
        ],
    },
)
def 玩家所有角色倒下时(game):
    """玩家的所有角色实体均倒下时，玩家实体的节点图上触发该事件"""
    玩家 = game.create_mock_entity("玩家1")
    return 玩家, "倒下原因_正常被击倒"
