from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询角色当前移动速度",
    category="查询节点",
    inputs=[("角色实体", "实体")],
    outputs=[("当前速度", "浮点数"), ("速度向量", "三维向量")],
    description="仅当角色拥有【监听移动速率】的单位状态效果时，才能查询",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询角色当前移动速度(game, 角色实体):
    """仅当角色拥有【监听移动速率】的单位状态效果时，才能查询"""
    return None  # Mock返回
