from __future__ import annotations

import time
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="暂停定时器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("定时器名称", "字符串")],
    outputs=[("流程出", "流程")],
    description="暂停指定目标实体上的指定定时器。之后可以使用【恢复定时器】节点恢复该定时器的计时",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 暂停定时器(game, 目标实体, 定时器名称):
    """暂停指定目标实体上的指定定时器。之后可以使用【恢复定时器】节点恢复该定时器的计时"""
    entity_id = game._get_entity_id(目标实体)
    timer_name = str(定时器名称 or "")
    timer_key = f"{entity_id}_{timer_name}"

    timers = getattr(game, "timers", None)
    if not isinstance(timers, dict):
        raise TypeError("暂停定时器：game.timers 必须为 dict")

    info = timers.get(timer_key, None)
    if not isinstance(info, dict):
        log_info("[定时器] 暂停定时器：未找到 timer_key={}", timer_key)
        return

    if bool(info.get("paused", False)):
        log_info("[定时器] 暂停定时器：已处于暂停状态 timer_key={}", timer_key)
        return

    now = float(time.monotonic())
    info["paused"] = True
    info["paused_at"] = float(now)
    # 将 next_fire_time 置为非数值，令 MockRuntime 的 tick() 自动跳过该定时器
    info["next_fire_time"] = None
    log_info("[定时器] 已暂停 timer_key={}", timer_key)
