from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="全局计时器触发时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("计时器名称", "字符串")],
    description="当倒计时的全局计时器计时结束时，会触发该事件 正计时的全局计时器不会触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 全局计时器触发时(game):
    """当倒计时的全局计时器计时结束时，会触发该事件 正计时的全局计时器不会触发该事件"""
    事件源 = game.get_entity("entity_1")
    return 事件源, "mock_guid_global_timer", "全局计时器1"
