from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询对局游玩方式及人数",
    category="查询节点",
    outputs=[("游玩人数", "整数"), ("游玩方式", "枚举")],
    description="查询进入对局的理论人数，即参与匹配或开房间的人数和进入对局的方式",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询对局游玩方式及人数():
    """查询进入对局的理论人数，即参与匹配或开房间的人数和进入对局的方式"""
    # Mock实现
    return 4, "匹配"  # 游玩人数, 游玩方式
