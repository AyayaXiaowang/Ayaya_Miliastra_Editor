from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="背包道具新增时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("道具持有者实体", "实体"), ("道具持有者GUID", "GUID"), ("道具配置ID", "配置ID"), ("获得数量", "整数")],
    description="背包内新增该道具时触发事件，背包组件的持有者可以收到。如果没有新增道具仅有数量变化则不会触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 背包道具新增时(game):
    """背包内新增该道具时触发事件，背包组件的持有者可以收到。如果没有新增道具仅有数量变化则不会触发该事件"""
    持有者 = game.create_mock_entity("玩家")
    return 持有者, "玩家_guid", "道具ID_001", 5
