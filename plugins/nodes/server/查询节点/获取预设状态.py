from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取预设状态",
    category="查询节点",
    inputs=[("目标实体", "实体"), ("预设状态索引", "整数")],
    outputs=[("预设状态值", "整数")],
    description="获取目标实体的指定预设状态的预设状态值。如果该实体没有指定的预设状态，则返回0",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取预设状态(game, 目标实体, 预设状态索引):
    """获取目标实体的指定预设状态的预设状态值。如果该实体没有指定的预设状态，则返回0"""
    return None  # 预设状态值
