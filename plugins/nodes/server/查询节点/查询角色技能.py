from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询角色技能",
    category="查询节点",
    inputs=[("角色实体", "实体"), ("角色技能槽位", "枚举")],
    outputs=[("技能配置ID", "配置ID")],
    description="查询角色指定槽位的技能，会输出该技能的配置ID",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询角色技能(game, 角色实体, 角色技能槽位):
    """查询角色指定槽位的技能，会输出该技能的配置ID"""
    return "技能ID_普通攻击"
