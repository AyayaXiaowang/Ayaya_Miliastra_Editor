from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体当前生效的扫描标签",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("扫描标签配置ID", "配置ID")],
    description="获取目标实体当前生效的扫描标签",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取实体当前生效的扫描标签(game, 目标实体):
    """获取目标实体当前生效的扫描标签"""
    return None  # 扫描标签配置ID
