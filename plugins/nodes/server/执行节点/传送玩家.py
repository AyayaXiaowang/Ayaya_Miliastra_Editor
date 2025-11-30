from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="传送玩家",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("目标位置", "三维向量"), ("目标旋转", "三维向量")],
    outputs=[("流程出", "流程")],
    description="传送指定玩家实体。会根据传送距离的远近决定是否有加载界面",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 传送玩家(game, 玩家实体, 目标位置, 目标旋转):
    """传送指定玩家实体。会根据传送距离的远近决定是否有加载界面"""
    entity_id = game._get_entity_id(玩家实体)
    entity = game.get_entity(entity_id)
    if entity:
        if isinstance(目标位置, (list, tuple)) and len(目标位置) == 3:
            entity.position = list(目标位置)
        if isinstance(目标旋转, (list, tuple)) and len(目标旋转) == 3:
            entity.rotation = list(目标旋转)
        log_info(f"[传送玩家] {entity.name} -> 位置{目标位置}, 旋转{目标旋转}")
        game.trigger_event("玩家传送完成时", 玩家实体)
