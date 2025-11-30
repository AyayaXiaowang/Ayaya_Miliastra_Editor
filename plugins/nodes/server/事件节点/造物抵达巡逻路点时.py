from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="造物抵达巡逻路点时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("造物实体", "实体"), ("造物GUID", "GUID"), ("当前巡逻模板序号", "整数"), ("当前路径索引", "整数"), ("当前抵达路点序号", "整数"), ("即将前往路点序号", "整数")],
    description="若在巡逻模板编辑中，勾选了指定路点的到达发送节点图事件选项，则会在满足条件时，收到该节点图事件 该节点图事件只能造物的节点图收到",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 造物抵达巡逻路点时(game):
    """若在巡逻模板编辑中，勾选了指定路点的到达发送节点图事件选项，则会在满足条件时，收到该节点图事件 该节点图事件只能造物的节点图收到"""
    造物 = game.create_mock_entity("巡逻造物")
    return 造物, "造物_guid", 0, 1, 3, 4
