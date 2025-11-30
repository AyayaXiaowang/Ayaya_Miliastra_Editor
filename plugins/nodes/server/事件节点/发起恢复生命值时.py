from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="发起恢复生命值时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("恢复目标实体", "实体"), ("恢复量", "浮点数"), ("恢复标签列表", "字符串列表")],
    description="实体向其他实体恢复生命值时，发起者实体上触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 发起恢复生命值时(game):
    """实体向其他实体恢复生命值时，发起者实体上触发该事件"""
    事件源 = game.create_mock_entity("治疗者")
    目标 = game.create_mock_entity("被治疗者")
    return 事件源, "治疗者_guid", 目标, 100.0, ["治疗"]
