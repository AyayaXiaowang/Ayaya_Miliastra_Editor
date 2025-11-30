from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="圆周率",
    category="查询节点",
    outputs=[("圆周率（π）", "浮点数")],
    description="返回圆周率π的近似值，约为3.142",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 圆周率():
    """返回圆周率π的近似值，约为3.142"""
    return math.pi
