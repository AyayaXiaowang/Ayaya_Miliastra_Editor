from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="移除实体",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体")],
    outputs=[("流程出", "流程")],
    description="移除指定实体，与销毁实体不同的是，不会有销毁表现，也不会触发销毁后才会触发的逻辑 移除实体不会触发【实体销毁时】事件，但可以触发【实体移除/销毁时】事件",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 移除实体(game, 目标实体):
    """移除指定实体，与销毁实体不同的是，不会有销毁表现，也不会触发销毁后才会触发的逻辑 移除实体不会触发【实体销毁时】事件，但可以触发【实体移除/销毁时】事件"""
    entity_id = game._get_entity_id(目标实体)
    if entity_id in game.entities:
        entity_name = game.entities[entity_id].name
        del game.entities[entity_id]
        log_info(f"[移除实体] {entity_name} (无销毁表现)")
        game.trigger_event("实体移除/销毁时", entity_id)
