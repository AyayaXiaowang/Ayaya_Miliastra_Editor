from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询当前环境时间",
    category="查询节点",
    outputs=[("当前环境时间", "浮点数"), ("当前循环天数", "整数")],
    description="查询当前的环境时间，范围为[0,24)",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询当前环境时间(game):
    """查询当前的环境时间，范围为[0,24)"""
    # Mock: 返回模拟时间
    return 12.5, 1
