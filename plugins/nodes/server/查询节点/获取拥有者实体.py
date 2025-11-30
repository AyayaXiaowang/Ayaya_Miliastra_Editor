from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取拥有者实体",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("拥有者实体", "实体")],
    description="获取指定目标实体的拥有者实体",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取拥有者实体(game, 目标实体):
    """获取指定目标实体的拥有者实体"""
    return None  # 拥有者实体
