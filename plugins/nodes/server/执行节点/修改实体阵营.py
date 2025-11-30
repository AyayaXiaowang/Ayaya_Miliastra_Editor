from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改实体阵营",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("阵营", "阵营")],
    outputs=[("流程出", "流程")],
    description="修改指定目标实体的阵营",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改实体阵营(game, 目标实体, 阵营):
    """修改指定目标实体的阵营"""
    log_info(f"[修改阵营] {目标实体} -> 阵营{阵营}")
    game.trigger_event("实体阵营变化时", 目标实体, 阵营)
