from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="文本气泡完成时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("气泡归属者实体", "实体"), ("角色实体", "实体"), ("文本气泡配置ID", "配置ID"), ("文本气泡完成次数", "整数")],
    description="该事件仅能被挂载文本气泡组件，且完成对话的实体节点图接收 完成的含义是最后一句对话播放完成",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 文本气泡完成时(game):
    """该事件仅能被挂载文本气泡组件，且完成对话的实体节点图接收 完成的含义是最后一句对话播放完成"""
    归属者 = game.create_mock_entity("NPC")
    角色 = game.create_mock_entity("角色")
    return 归属者, 角色, "对话ID_001", 1
