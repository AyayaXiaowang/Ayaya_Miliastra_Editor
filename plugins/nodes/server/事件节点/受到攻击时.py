from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="受到攻击时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("攻击者实体", "实体"), ("伤害量", "浮点数"), ("攻击标签列表", "字符串列表"), ("元素类型", "枚举"), ("元素攻击强效", "浮点数")],
    description="实体受到攻击时触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 受到攻击时(game):
    """实体受到攻击时触发该事件"""
    事件源 = game.create_mock_entity("受击者")
    攻击者 = game.create_mock_entity("攻击者")
    return 事件源, "受击者_guid", 攻击者, 50.0, ["普通攻击"], "物理", 1.0
