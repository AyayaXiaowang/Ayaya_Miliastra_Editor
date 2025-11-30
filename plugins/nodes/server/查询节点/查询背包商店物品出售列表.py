from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询背包商店物品出售列表",
    category="查询节点",
    inputs=[("商店归属者实体", "实体"), ("商店序号", "整数")],
    outputs=[("道具配置ID列表", "配置ID列表")],
    description="查询背包商店物品出售列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询背包商店物品出售列表(game, 商店归属者实体, 商店序号):
    """查询背包商店物品出售列表"""
    return ["道具A", "道具B", "道具C"]
