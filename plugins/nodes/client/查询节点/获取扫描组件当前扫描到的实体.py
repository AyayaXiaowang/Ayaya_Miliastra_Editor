from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取扫描组件当前扫描到的实体",
    category="查询节点",
    outputs=[("对应实体", "实体"), ("扫描标签配置ID", "配置ID")],
    description="获取扫描组件当前扫描到的实体，指扫描状态为“激活状态”的实体",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取扫描组件当前扫描到的实体():
    """获取扫描组件当前扫描到的实体，指扫描状态为“激活状态”的实体"""
    return None, None  # 对应实体, 扫描标签配置ID
