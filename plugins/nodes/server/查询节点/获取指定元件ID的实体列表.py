from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取指定元件ID的实体列表",
    category="查询节点",
    inputs=[("目标实体列表", "实体列表"), ("元件ID", "元件ID")],
    outputs=[("结果列表", "实体列表")],
    description="在目标实体列表中获取以指定元件ID创建的实体列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取指定元件ID的实体列表(game, 目标实体列表, 元件ID):
    """在目标实体列表中获取以指定元件ID创建的实体列表"""
    return None  # 结果列表
