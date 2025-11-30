from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取目标实体",
    category="查询节点",
    outputs=[("目标实体", "实体")],
    description="获取目标实体，根据过滤器节点图被引用的功能模块不同，其指代含义会有区别",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取目标实体():
    """获取目标实体，根据过滤器节点图被引用的功能模块不同，其指代含义会有区别"""
    # Mock: 返回一个模拟目标实体
    return "mock_target_entity"
