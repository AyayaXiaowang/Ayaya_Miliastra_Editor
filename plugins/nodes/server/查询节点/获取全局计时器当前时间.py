from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取全局计时器当前时间",
    category="查询节点",
    inputs=[("目标实体", "实体"), ("计时器名称", "字符串")],
    outputs=[("当前时间", "浮点数")],
    description="获取目标实体上指定全局计时器的当前时间",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取全局计时器当前时间(game, 目标实体, 计时器名称):
    """获取目标实体上指定全局计时器的当前时间"""
    return 30.0
