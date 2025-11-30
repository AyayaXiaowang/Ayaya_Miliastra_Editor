from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="界面控件组触发时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("界面控件组组合索引", "整数"), ("界面控件组索引", "整数")],
    description="只有交互按钮和道具展示类型的界面控件，才会触发本事件 在关卡运行中，通过交互按钮或道具展示界面控件制作的界面控件组，被执行交互操作会发送节点图事件”界面控件组触发时“，此事件只有触发交互的玩家节点图可以获取",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 界面控件组触发时(game):
    """只有交互按钮和道具展示类型的界面控件，才会触发本事件 在关卡运行中，通过交互按钮或道具展示界面控件制作的界面控件组，被执行交互操作会发送节点图事件"界面控件组触发时"，此事件只有触发交互的玩家节点图可以获取"""
    玩家 = game.create_mock_entity("玩家")
    return 玩家, "玩家_guid", 1, 0
