from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取局部变量",
    category="查询节点",
    inputs=[("变量名", "字符串")],
    outputs=[("变量值", "泛型")],
    description="获取特定局部变量的变量值",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取局部变量(game, 变量名):
    """获取特定局部变量的变量值"""
    # 局部变量在生成阶段被处理为Python变量
    return None  # 变量值（由代码生成器处理）
