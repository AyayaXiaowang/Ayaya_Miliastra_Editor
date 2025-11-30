from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取玩家当前界面布局",
    category="查询节点",
    inputs=[("玩家实体", "实体")],
    outputs=[("布局索引", "整数")],
    description="获取指定玩家实体上当前生效的界面布局的索引",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取玩家当前界面布局(game, 玩家实体):
    """获取指定玩家实体上当前生效的界面布局的索引"""
    return 0
