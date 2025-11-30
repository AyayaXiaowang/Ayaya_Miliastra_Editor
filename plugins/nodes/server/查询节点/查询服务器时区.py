from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询服务器时区",
    category="查询节点",
    outputs=[("时区", "整数")],
    description="可以查询服务器的时区",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询服务器时区():
    """可以查询服务器的时区"""
    return 8  # Mock: UTC+8
