from __future__ import annotations

import time
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="恢复定时器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("定时器名称", "字符串")],
    outputs=[("流程出", "流程")],
    description="使目标实体上一个处于暂停状态的定时器恢复运行",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 恢复定时器(game, 目标实体, 定时器名称):
    """使目标实体上一个处于暂停状态的定时器恢复运行"""
    entity_id = game._get_entity_id(目标实体)
    timer_name = str(定时器名称 or "")
    timer_key = f"{entity_id}_{timer_name}"

    timers = getattr(game, "timers", None)
    if not isinstance(timers, dict):
        raise TypeError("恢复定时器：game.timers 必须为 dict")

    info = timers.get(timer_key, None)
    if not isinstance(info, dict):
        log_info("[定时器] 恢复定时器：未找到 timer_key={}", timer_key)
        return

    if not bool(info.get("paused", False)):
        log_info("[定时器] 恢复定时器：定时器不在暂停状态 timer_key={}", timer_key)
        return

    paused_at = info.get("paused_at", None)
    if not isinstance(paused_at, (int, float)):
        raise ValueError("恢复定时器：缺少 paused_at（无法计算暂停时长）")

    start_time = info.get("start_time", None)
    if not isinstance(start_time, (int, float)):
        raise ValueError("恢复定时器：缺少 start_time（无法恢复计时）")

    seq = info.get("sequence", None)
    if not isinstance(seq, list) or (not seq):
        raise ValueError("恢复定时器：缺少 sequence（无法恢复触发计划）")

    now = float(time.monotonic())
    delta = float(now) - float(paused_at)
    if delta < 0:
        delta = 0.0

    # 将 start_time 整体右移 pause_duration，以保持“序列时间点”相对进度不变。
    new_start_time = float(start_time) + float(delta)
    info["start_time"] = float(new_start_time)

    loop_count = int(info.get("loop_count", 0))
    next_index = int(info.get("next_index", 0))
    if next_index < 0:
        next_index = 0
    if next_index >= len(seq):
        next_index = max(0, len(seq) - 1)
        info["next_index"] = int(next_index)

    loop_duration = info.get("loop_duration", None)
    if not isinstance(loop_duration, (int, float)):
        loop_duration = float(seq[-1])
        info["loop_duration"] = float(loop_duration)

    info["next_fire_time"] = float(new_start_time) + loop_count * float(loop_duration) + float(seq[next_index])
    info["paused"] = False
    if "paused_at" in info:
        del info["paused_at"]

    log_info("[定时器] 已恢复 timer_key={}", timer_key)
