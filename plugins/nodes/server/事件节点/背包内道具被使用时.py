from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="背包内道具被使用时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("道具持有者实体", "实体"), ("道具持有者GUID", "GUID"), ("道具配置ID", "配置ID"), ("使用数量", "整数")],
    description="背包内道具被使用时触发该事件，背包组件的持有者可以收到",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 背包内道具被使用时(game):
    """背包内道具被使用时触发该事件，背包组件的持有者可以收到"""
    持有者 = game.create_mock_entity("玩家")
    return 持有者, "玩家_guid", "药水ID", 1
