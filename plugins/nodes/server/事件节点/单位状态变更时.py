from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="单位状态变更时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("单位状态配置ID", "配置ID"), ("施加者实体", "实体"), ("持续时间是否无限", "布尔值"), ("状态剩余时长", "浮点数"), ("状态剩余层数", "整数"), ("状态原始层数", "整数"), ("槽位序号", "整数")],
    description="单位状态的层数发生变化时，触发该事件 单位状态的施加以及移除都会触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 单位状态变更时(game):
    """单位状态的层数发生变化时，触发该事件 单位状态的施加以及移除都会触发该事件"""
    事件源 = game.create_mock_entity("实体")
    施加者 = game.create_mock_entity("施加者")
    return 事件源, "实体_guid", "状态ID", 施加者, False, 10.0, 3, 5, 0
