from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取指定实体的仇恨目标",
    category="查询节点",
    inputs=[("指定实体", "实体")],
    outputs=[("仇恨目标", "实体")],
    description="获取指定实体的仇恨目标",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取指定实体的仇恨目标(game, 指定实体):
    """获取指定实体的仇恨目标"""
    return None  # 仇恨目标
