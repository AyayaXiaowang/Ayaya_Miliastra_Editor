from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取当前生效的扫描标签配置ID",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("扫描标签配置ID", "配置ID")],
    description="获取目标实体上当前生效的扫描标签的配置ID",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取当前生效的扫描标签配置ID(game, 目标实体):
    """获取目标实体上当前生效的扫描标签的配置ID"""
    return "scan_tag_001"
