from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="角色倒下时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("角色实体", "实体"), ("原因", "枚举"), ("击倒者实体", "实体")],
    description="角色倒下时，角色实体上的节点图可以触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 角色倒下时(game):
    """角色倒下时，角色实体上的节点图可以触发该事件"""
    角色 = game.create_mock_entity("角色")
    击倒者 = game.create_mock_entity("敌人")
    return 角色, "生命值归零", 击倒者
