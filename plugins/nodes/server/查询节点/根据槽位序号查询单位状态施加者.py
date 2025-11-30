from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="根据槽位序号查询单位状态施加者",
    category="查询节点",
    inputs=[("查询目标实体", "实体"), ("单位状态配置ID", "配置ID"), ("槽位序号", "整数")],
    outputs=[("施加者实体", "实体")],
    description="查询目标实体指定槽位上的特定单位状态的施加者",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 根据槽位序号查询单位状态施加者(game, 查询目标实体, 单位状态配置ID, 槽位序号):
    """查询目标实体指定槽位上的特定单位状态的施加者"""
    return game.create_mock_entity("施加者")
