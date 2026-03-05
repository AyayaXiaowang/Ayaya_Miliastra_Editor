from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="提升玩家当前职业经验",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家", "实体"), ("经验值", "整数")],
    outputs=[("流程出", "流程")],
    description="提升玩家当前职业经验，超出最大等级的部分会无效",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 提升玩家当前职业经验(game, 目标玩家, 经验值):
    """提升玩家当前职业经验，超出最大等级的部分会无效"""
    profession_id = game.get_custom_variable(目标玩家, "当前职业配置ID", "职业ID_战士")
    var_name = f"职业经验_{profession_id}"

    old_exp = game.get_custom_variable(目标玩家, var_name, 0)
    delta = int(经验值)
    new_exp = int(old_exp) + int(delta)

    game.set_custom_variable(目标玩家, var_name, int(new_exp), trigger_event=True)
    log_info("[提升玩家当前职业经验] profession_id={}, {} + {} = {}", profession_id, int(old_exp), int(delta), int(new_exp))
