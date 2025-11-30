from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="仇恨目标变化时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("变化前仇恨目标", "实体"), ("变化后仇恨目标", "实体")],
    description="仅自定义仇恨模式可用 仇恨目标发生变化时，触发该事件 入战和脱战也可以触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 仇恨目标变化时(game):
    """仅自定义仇恨模式可用 仇恨目标发生变化时，触发该事件 入战和脱战也可以触发该事件"""
    事件源 = game.create_mock_entity("实体")
    旧目标 = game.create_mock_entity("旧仇恨目标")
    新目标 = game.create_mock_entity("新仇恨目标")
    return 事件源, "实体_guid", 旧目标, 新目标
