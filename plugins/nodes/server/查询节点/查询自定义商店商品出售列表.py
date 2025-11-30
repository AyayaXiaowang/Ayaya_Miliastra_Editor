from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询自定义商店商品出售列表",
    category="查询节点",
    inputs=[("商店归属者实体", "实体"), ("商店序号", "整数")],
    outputs=[("商品序号列表", "整数列表")],
    description="查询自定义商店商品出售列表，出参为商品序号组成的列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询自定义商店商品出售列表(game, 商店归属者实体, 商店序号):
    """查询自定义商店商品出售列表，出参为商品序号组成的列表"""
    return [0, 1, 2]
