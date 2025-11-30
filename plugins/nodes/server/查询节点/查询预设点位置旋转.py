from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询预设点位置旋转",
    category="查询节点",
    inputs=[("点位索引", "整数")],
    outputs=[("位置", "三维向量"), ("旋转", "三维向量")],
    description="查询指定预设点的位置和旋转",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询预设点位置旋转(game, 点位索引):
    """查询指定预设点的位置和旋转"""
    return [50.0, 0.0, 25.0], [0.0, 0.0, 0.0]
