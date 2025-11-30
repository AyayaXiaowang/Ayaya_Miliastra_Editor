from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询时间戳（UTC+0时区）",
    category="查询节点",
    outputs=[("时间戳", "整数")],
    description="可以查询当前的时间戳",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询时间戳_UTC_0时区():
    """可以查询当前的时间戳"""
    return int(time.time())
