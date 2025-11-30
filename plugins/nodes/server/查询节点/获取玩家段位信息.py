from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取玩家段位信息",
    category="查询节点",
    inputs=[("玩家实体", "实体")],
    outputs=[("玩家段位总分", "整数"), ("玩家连胜次数", "整数"), ("玩家连败次数", "整数"), ("玩家连续逃跑次数", "整数")],
    description="获取玩家段位相关信息",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取玩家段位信息(game, 玩家实体):
    """获取玩家段位相关信息"""
    return {"段位": "白银", "分数": 1500}
