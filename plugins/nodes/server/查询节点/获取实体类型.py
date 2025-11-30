from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体类型",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("实体类型", "枚举")],
    description="获取目标实体的实体类型",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取实体类型(game, 目标实体):
    """获取目标实体的实体类型"""
    return None  # 实体类型
