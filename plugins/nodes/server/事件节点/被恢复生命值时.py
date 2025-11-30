from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="被恢复生命值时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("治疗者实体", "实体"), ("恢复量", "浮点数"), ("恢复标签列表", "字符串列表")],
    description="实体被恢复生命值时，触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 被恢复生命值时(game):
    """实体被恢复生命值时，触发该事件"""
    事件源 = game.create_mock_entity("被治疗者")
    治疗者 = game.create_mock_entity("治疗者")
    return 事件源, "被治疗者_guid", 治疗者, 100.0, ["治疗"]
