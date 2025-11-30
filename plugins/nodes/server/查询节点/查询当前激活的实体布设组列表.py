from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询当前激活的实体布设组列表",
    category="查询节点",
    outputs=[("实体布设组索引列表", "整数列表")],
    description="查询当前关卡激活的实体布设组组成的列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询当前激活的实体布设组列表(game):
    """查询当前关卡激活的实体布设组组成的列表"""
    return [0, 1, 2]
