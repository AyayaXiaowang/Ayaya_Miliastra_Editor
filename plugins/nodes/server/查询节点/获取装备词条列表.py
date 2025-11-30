from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取装备词条列表",
    category="查询节点",
    inputs=[("装备索引", "整数")],
    outputs=[("装备词条列表", "整数列表")],
    description="获取该装备实例的所有词条组成的列表 装备初始化时，词条的数值会发生随机，所以装备实例上的装备词条也会生成对应的实例，故数据类型为整数而不是配置ID",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取装备词条列表(game, 装备索引):
    """获取该装备实例的所有词条组成的列表 装备初始化时，词条的数值会发生随机，所以装备实例上的装备词条也会生成对应的实例，故数据类型为整数而不是配置ID"""
    return [0, 1, 2]
