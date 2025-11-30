from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="基础运动器停止时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("运动器名称", "字符串")],
    description="基础运动器组件上的某个基础运动器完成运动时或被关闭时向组件持有者发送该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 基础运动器停止时(game):
    """基础运动器组件上的某个基础运动器完成运动时或被关闭时向组件持有者发送该事件"""
    事件源 = game.create_mock_entity("运动实体")
    return 事件源, "运动实体_guid", "运动器1"
