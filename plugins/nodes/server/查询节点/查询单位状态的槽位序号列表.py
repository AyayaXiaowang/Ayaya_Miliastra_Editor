from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询单位状态的槽位序号列表",
    category="查询节点",
    inputs=[("查询目标实体", "实体"), ("单位状态配置ID", "配置ID")],
    outputs=[("槽位序号列表", "整数列表")],
    description="查询指定目标实体上特定配置ID的单位状态的所有槽位序号列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询单位状态的槽位序号列表(game, 查询目标实体, 单位状态配置ID):
    """查询指定目标实体上特定配置ID的单位状态的所有槽位序号列表"""
    return [0, 2]
