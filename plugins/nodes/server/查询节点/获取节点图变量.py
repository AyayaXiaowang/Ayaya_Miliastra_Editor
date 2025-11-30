from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取节点图变量",
    category="查询节点",
    inputs=[("变量名", "字符串")],
    outputs=[("变量值", "泛型")],
    description="获取当前节点图的指定节点图变量的值 如果变量不存在，则返回类型的默认值",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取节点图变量(game, 变量名):
    """获取当前节点图的指定节点图变量的值 如果变量不存在，则返回类型的默认值"""
    return game.get_graph_variable(变量名, None)
