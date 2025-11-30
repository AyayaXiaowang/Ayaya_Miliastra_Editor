from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取背包货币数量",
    category="查询节点",
    inputs=[("背包持有者实体", "实体"), ("货币配置ID", "配置ID")],
    outputs=[("资源数量", "整数")],
    description="获取背包内特定配置ID的货币数量",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取背包货币数量(game, 背包持有者实体, 货币配置ID):
    """获取背包内特定配置ID的货币数量"""
    return 10000
