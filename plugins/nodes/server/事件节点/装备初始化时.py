from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="装备初始化时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("装备持有者", "实体"), ("装备持有者GUID", "GUID"), ("装备索引", "整数")],
    description="当装备首次被获取进入背包时，会进行初始化，此时事件出参会返回装备实例的唯一索引，通过此索引即可对装备进行动态修改。装备的持有者可以收到该事件，需要配置在道具节点图里",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 装备初始化时(game):
    """当装备首次被获取进入背包时，会进行初始化，此时事件出参会返回装备实例的唯一索引，通过此索引即可对装备进行动态修改。装备的持有者可以收到该事件，需要配置在道具节点图里"""
    持有者 = game.create_mock_entity("玩家")
    return 持有者, "玩家_guid", 10001
