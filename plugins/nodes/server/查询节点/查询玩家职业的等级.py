from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询玩家职业的等级",
    category="查询节点",
    inputs=[("玩家实体", "实体"), ("职业配置ID", "配置ID")],
    outputs=[("等级", "整数")],
    description="查询玩家指定职业的等级",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询玩家职业的等级(game, 玩家实体, 职业配置ID):
    """查询玩家指定职业的等级"""
    var_name = f"职业等级_{职业配置ID}"
    level = game.get_custom_variable(玩家实体, var_name, 1)
    return int(level)
