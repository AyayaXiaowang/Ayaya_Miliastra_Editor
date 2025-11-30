from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="路径到达路点时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("运动器名称", "字符串"), ("路径点序号", "整数")],
    description="路径运动器到达路点时发送给基础运动器组件的持有者，需要在路点配置中配置“到达路点发送事件”才会触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 路径到达路点时(game):
    """路径运动器到达路点时发送给基础运动器组件的持有者，需要在路点配置中配置"到达路点发送事件"才会触发该事件"""
    事件源 = game.create_mock_entity("路径实体")
    return 事件源, "路径实体_guid", "路径运动器1", 2
