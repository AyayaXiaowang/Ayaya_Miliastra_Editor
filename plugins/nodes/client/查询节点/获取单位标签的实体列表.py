from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取单位标签的实体列表",
    category="查询节点",
    inputs=[("单位标签索引", "整数")],
    outputs=[("实体列表", "实体列表")],
    description="获取在场所有携带该单位标签的实体列表",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取单位标签的实体列表(单位标签索引):
    """获取在场所有携带该单位标签的实体列表"""
    return None  # 实体列表
