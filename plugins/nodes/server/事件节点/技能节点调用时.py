from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="技能节点调用时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("调用者实体", "实体"), ("调用者GUID", "GUID"), ("参数1", "字符串"), ("参数2", "字符串"), ("参数3", "字符串")],
    description="通过技能节点图的【通知服务器节点图】节点触发，可以传入三个字符串类型的值",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 技能节点调用时(game):
    """通过技能节点图的【通知服务器节点图】节点触发，可以传入三个字符串类型的值"""
    调用者 = game.create_mock_entity("技能释放者")
    return 调用者, "调用者_guid", "参数1", "参数2", "参数3"
