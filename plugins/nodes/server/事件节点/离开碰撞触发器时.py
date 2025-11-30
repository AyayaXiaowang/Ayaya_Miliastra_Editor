from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="离开碰撞触发器时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("离开者实体", "实体"), ("离开者实体GUID", "GUID"), ("触发器实体", "实体"), ("触发器实体GUID", "GUID"), ("触发器序号", "整数")],
    description="运行中实体A的“碰撞触发源”范围，离开其他运行中实体B的“碰撞触发器”范围 会发送节点图事件给配置“碰撞触发器”的实体B",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 离开碰撞触发器时(game):
    """运行中实体A的"碰撞触发源"范围，离开其他运行中实体B的"碰撞触发器"范围 会发送节点图事件给配置"碰撞触发器"的实体B"""
    离开者 = game.create_mock_entity("离开者")
    触发器 = game.create_mock_entity("触发器实体")
    return 离开者, "离开者_guid", 触发器, "触发器_guid", 0
