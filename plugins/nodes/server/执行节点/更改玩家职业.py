from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="更改玩家职业",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家", "实体"), ("职业配置ID", "配置ID")],
    outputs=[("流程出", "流程")],
    description="修改玩家的当前职业为配置ID对应的职业",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 更改玩家职业(game, 目标玩家, 职业配置ID):
    """修改玩家的当前职业为配置ID对应的职业"""
    new_profession_id = str(职业配置ID or "")
    old_profession_id = game.get_custom_variable(目标玩家, "当前职业配置ID", "")

    if old_profession_id != new_profession_id:
        if str(old_profession_id or ""):
            game.trigger_event(
                "玩家职业解除时",
                事件源实体=目标玩家,
                事件源GUID=0,
                更改前职业配置ID=old_profession_id,
                更改后职业配置ID=new_profession_id,
            )

        game.set_custom_variable(目标玩家, "当前职业配置ID", new_profession_id, trigger_event=True)
        game.trigger_event(
            "玩家职业更改时",
            事件源实体=目标玩家,
            事件源GUID=0,
            更改前职业配置ID=old_profession_id,
            更改后职业配置ID=new_profession_id,
        )

    log_info(
        "[更改玩家职业] old={}, new={}",
        str(old_profession_id or "<empty>"),
        str(new_profession_id or "<empty>"),
    )
