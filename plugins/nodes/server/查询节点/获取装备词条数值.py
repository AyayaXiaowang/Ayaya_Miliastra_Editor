from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取装备词条数值",
    category="查询节点",
    inputs=[("装备索引", "整数"), ("词条序号", "整数")],
    outputs=[("装备数值", "浮点数")],
    description="获取装备实例上对应序号词条的数值",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取装备词条数值(game, 装备索引, 词条序号):
    """获取装备实例上对应序号词条的数值"""
    return 50.0
