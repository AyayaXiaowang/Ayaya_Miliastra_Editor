from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取跟随运动器的目标",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("跟随目标实体", "实体"), ("跟随目标GUID", "GUID")],
    description="获取跟随运动器的目标，可以获取目标实体和实体的GUID",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取跟随运动器的目标(game, 目标实体):
    """获取跟随运动器的目标，可以获取目标实体和实体的GUID"""
    目标 = game.create_mock_entity("跟随目标")
    return 目标, "目标_guid"
