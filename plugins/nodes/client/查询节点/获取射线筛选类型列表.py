from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取射线筛选类型列表",
    category="查询节点",
    outputs=[("列表", "枚举列表")],
    description="将所需的射线筛选类型拼装为一个列表。可筛选项有受击盒、场景、物件自身碰撞",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取射线筛选类型列表():
    """将所需的射线筛选类型拼装为一个列表。可筛选项有受击盒、场景、物件自身碰撞"""
    # Mock: 返回所有筛选类型
    return ["受击盒", "场景", "物件自身碰撞"]
