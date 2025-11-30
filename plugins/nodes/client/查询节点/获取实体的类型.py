from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体的类型",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("实体类型", "枚举")],
    description="获取指定实体的类型",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取实体的类型(game, 目标实体):
    """获取指定实体的类型"""
    # Mock: 返回模拟实体类型
    return "物件"  # 可能的类型: 关卡、物件、玩家、角色、造物
