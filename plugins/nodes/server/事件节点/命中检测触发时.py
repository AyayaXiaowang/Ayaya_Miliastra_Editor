from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="命中检测触发时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("是否命中受击盒", "布尔值"), ("命中实体", "实体"), ("命中位置", "三维向量")],
    description="命中检测组件命中其他实体或场景时组件的持有者触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 命中检测触发时(game):
    """命中检测组件命中其他实体或场景时组件的持有者触发该事件"""
    事件源 = game.create_mock_entity("检测实体")
    命中实体 = game.create_mock_entity("被命中实体")
    return 事件源, "检测实体_guid", True, 命中实体, [10.0, 0, 5.0]
