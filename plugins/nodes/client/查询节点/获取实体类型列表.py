from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体类型列表",
    category="查询节点",
    outputs=[("列表", "枚举列表")],
    description="将所需的实体类型拼装为一个列表。类型分为关卡、物件、玩家、角色、造物",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取实体类型列表():
    """将所需的实体类型拼装为一个列表。类型分为关卡、物件、玩家、角色、造物"""
    # Mock: 返回所有实体类型
    return ["关卡", "物件", "玩家", "角色", "造物"]
