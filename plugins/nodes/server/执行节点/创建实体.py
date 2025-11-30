from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="创建实体",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标GUID", "GUID"), ("单位标签索引列表", "整数列表")],
    outputs=[("流程出", "流程")],
    description="根据GUID创建实体。要求预先将其布设在场景内",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 创建实体(game, 目标GUID, 单位标签索引列表):
    """根据GUID创建实体。要求预先将其布设在场景内"""
    新实体 = game.create_mock_entity(f"实体_{目标GUID}")
    return 新实体
