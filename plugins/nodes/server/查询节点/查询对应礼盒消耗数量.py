from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询对应礼盒消耗数量",
    category="查询节点",
    inputs=[("数量", "整数")],
    outputs=[("玩家实体", "实体"), ("礼盒索引", "整数")],
    description="查询玩家实体上指定礼盒的消耗数量",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询对应礼盒消耗数量(game, 玩家实体, 礼盒索引):
    """查询玩家实体上指定礼盒的消耗数量"""
    return 玩家实体, 2
