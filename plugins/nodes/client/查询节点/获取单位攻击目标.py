from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取单位攻击目标",
    category="查询节点",
    inputs=[("单位实体", "实体")],
    outputs=[("攻击目标实体", "实体")],
    description="获取单位实体当前正在攻击的目标实体",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取单位攻击目标(game, 单位实体):
    """获取单位实体当前正在攻击的目标实体"""
    # Mock: 返回一个模拟攻击目标
    return game.get_entity("entity_1")
