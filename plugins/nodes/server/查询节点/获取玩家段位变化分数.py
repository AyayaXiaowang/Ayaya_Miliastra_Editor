from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取玩家段位变化分数",
    category="查询节点",
    inputs=[("玩家实体", "实体"), ("结算状态", "枚举")],
    outputs=[("分数", "整数")],
    description="获取玩家实体在不同结算状态下段位的变化分数",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取玩家段位变化分数(game, 玩家实体, 结算状态):
    """获取玩家实体在不同结算状态下段位的变化分数"""
    return 100
