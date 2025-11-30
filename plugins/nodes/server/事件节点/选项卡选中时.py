from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="选项卡选中时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("选项卡序号", "整数"), ("选择者实体", "实体")],
    description="生效的选项卡被选中后，会向节点图发送事件 配置选项卡组件的实体节点图，会接收该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 选项卡选中时(game):
    """生效的选项卡被选中后，会向节点图发送事件 配置选项卡组件的实体节点图，会接收该事件"""
    事件源 = game.create_mock_entity("选项卡实体")
    选择者 = game.create_mock_entity("玩家")
    return 事件源, "实体_guid", 2, 选择者
