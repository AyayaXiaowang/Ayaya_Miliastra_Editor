from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="以单位标签获取预设点位列表",
    category="查询节点",
    inputs=[("单位标签索引", "整数")],
    outputs=[("点位索引列表", "整数列表")],
    description="根据单位标签索引查询所有携带该单位标签的预设点位列表，输出值为该预设点位的索引",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 以单位标签获取预设点位列表(game, 单位标签索引):
    """根据单位标签索引查询所有携带该单位标签的预设点位列表，输出值为该预设点位的索引"""
    return [0, 1, 2]
