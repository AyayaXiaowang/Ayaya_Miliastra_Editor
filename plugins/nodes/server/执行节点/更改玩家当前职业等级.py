from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="更改玩家当前职业等级",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家", "实体"), ("等级", "整数")],
    outputs=[("流程出", "流程")],
    description="修改玩家当前职业等级，若超出定义的等级范围则会失效",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 更改玩家当前职业等级(game, 目标玩家, 等级):
    """修改玩家当前职业等级，若超出定义的等级范围则会失效"""
    profession_id = game.get_custom_variable(目标玩家, "当前职业配置ID", "职业ID_战士")
    var_name = f"职业等级_{profession_id}"

    old_level = game.get_custom_variable(目标玩家, var_name, 1)
    new_level = int(等级)

    game.set_custom_variable(目标玩家, var_name, int(new_level), trigger_event=True)
    game.trigger_event(
        "玩家职业等级变化时",
        事件源实体=目标玩家,
        事件源GUID=0,
        变化前等级=int(old_level),
        变化后等级=int(new_level),
    )

    log_info("[更改玩家当前职业等级] profession_id={}, {} -> {}", profession_id, int(old_level), int(new_level))
