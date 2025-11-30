from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询实体是否具有单位状态",
    category="查询节点",
    inputs=[("目标实体", "实体"), ("单位状态配置ID", "配置ID")],
    outputs=[("是否具有", "布尔值")],
    description="查询指定实体是否具有特定配置ID的单位状态",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询实体是否具有单位状态(game, 目标实体, 单位状态配置ID):
    """查询指定实体是否具有特定配置ID的单位状态"""
    return True
