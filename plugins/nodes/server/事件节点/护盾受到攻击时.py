from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="护盾受到攻击时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("攻击者实体", "实体"), ("攻击者GUID", "GUID"), ("单位状态配置ID", "配置ID"), ("攻击前层数", "整数"), ("攻击后层数", "整数"), ("攻击前该单位状态的护盾含量", "浮点数"), ("攻击后该单位状态的护盾含量", "浮点数")],
    description="为实体添加单位状态效果【添加护盾】，受到攻击时触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 护盾受到攻击时(game):
    """为实体添加单位状态效果【添加护盾】，受到攻击时触发该事件"""
    事件源 = game.create_mock_entity("护盾持有者")
    攻击者 = game.create_mock_entity("攻击者")
    return 事件源, "持有者_guid", 攻击者, "攻击者_guid", "护盾状态ID", 5, 3, 500.0, 300.0
