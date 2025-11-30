from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取指定路径点信息",
    category="查询节点",
    inputs=[("路径索引", "整数"), ("路径路点序号", "整数")],
    outputs=[("路点位置", "三维向量"), ("路点朝向", "三维向量")],
    description="查询指定路径的特定路点信息",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取指定路径点信息(game, 路径索引, 路径路点序号):
    """查询指定路径的特定路点信息"""
    return [100.0, 0.0, 50.0], [0.0, 90.0, 0.0]
