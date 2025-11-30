from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="定时器触发时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("定时器名称", "字符串"), ("定时器序列序号", "整数"), ("循环次数", "整数")],
    description="定时器运行到指定时间节点时，触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 定时器触发时(game):
    """定时器运行到指定时间节点时，触发该事件"""
    事件源 = game.get_entity("entity_1")
    return 事件源, "mock_guid_timer", "定时器1", 1, 0
