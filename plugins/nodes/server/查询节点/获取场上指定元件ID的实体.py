from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取场上指定元件ID的实体",
    category="查询节点",
    inputs=[("元件ID", "元件ID")],
    outputs=[("实体列表", "实体列表")],
    description="获取当前场上通过指定元件ID创建的所有实体",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取场上指定元件ID的实体(game, 元件ID):
    """获取当前场上通过指定元件ID创建的所有实体"""
    # Mock: 返回匹配的实体列表
    return [e for e in game.entities.values() if hasattr(e, 'component_id') and e.component_id == 元件ID]
