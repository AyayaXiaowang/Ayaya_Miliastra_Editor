from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="发生元素反应事件时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("元素反应类型", "枚举"), ("触发者实体", "实体"), ("触发者GUID", "GUID")],
    description="为实体添加单位状态效果【监听元素反应】，达成条件会触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 发生元素反应事件时(game):
    """为实体添加单位状态效果【监听元素反应】，达成条件会触发该事件"""
    事件源 = game.create_mock_entity("实体")
    触发者 = game.create_mock_entity("触发者")
    return 事件源, "实体_guid", "蒸发", 触发者, "触发者_guid"
