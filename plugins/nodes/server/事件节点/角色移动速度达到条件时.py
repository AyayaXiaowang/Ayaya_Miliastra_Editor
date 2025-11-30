from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="角色移动速度达到条件时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("单位状态配置ID", "配置ID"), ("条件：比较类型", "枚举"), ("条件：比较值", "浮点数"), ("当前移动速度", "浮点数")],
    description="为角色实体添加单位状态效果【监听移动速率】，达成条件会触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 角色移动速度达到条件时(game):
    """为角色实体添加单位状态效果【监听移动速率】，达成条件会触发该事件"""
    事件源 = game.create_mock_entity("角色")
    return 事件源, "角色_guid", "移动速度监听状态", "大于", 5.0, 5.5
