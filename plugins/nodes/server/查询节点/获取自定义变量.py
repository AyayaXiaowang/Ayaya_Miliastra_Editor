from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取自定义变量",
    category="查询节点",
    inputs=[("目标实体", "实体"), ("变量名", "字符串")],
    outputs=[("变量值", "泛型")],
    description="获取目标实体的指定自定义变量的值 如果变量不存在，则返回类型的默认值",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取自定义变量(game, 目标实体, 变量名):
    """获取目标实体的指定自定义变量的值 如果变量不存在，则返回类型的默认值"""
    return game.get_custom_variable(目标实体, 变量名, None)
