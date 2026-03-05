from __future__ import annotations

import time
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取全局计时器当前时间",
    category="查询节点",
    inputs=[("目标实体", "实体"), ("计时器名称", "字符串")],
    outputs=[("当前时间", "浮点数")],
    description="获取目标实体上指定全局计时器的当前时间",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取全局计时器当前时间(game, 目标实体, 计时器名称):
    """获取目标实体上指定全局计时器的当前时间"""
    entity_id = game._get_entity_id(目标实体)
    timer_name = str(计时器名称 or "")
    timer_key = f"{entity_id}_{timer_name}"

    timers = getattr(game, "timers", None)
    if not isinstance(timers, dict):
        raise TypeError("获取全局计时器当前时间：game.timers 必须为 dict")

    info = timers.get(timer_key, None)
    if not isinstance(info, dict):
        return 0.0

    start_time = info.get("start_time", None)
    if not isinstance(start_time, (int, float)):
        return 0.0

    now = float(time.monotonic())
    if bool(info.get("paused", False)):
        paused_at = info.get("paused_at", None)
        if isinstance(paused_at, (int, float)):
            now = float(paused_at)

    elapsed = float(now) - float(start_time)
    if elapsed < 0:
        elapsed = 0.0

    is_loop = bool(info.get("is_loop", False))
    if is_loop:
        loop_duration = info.get("loop_duration", None)
        if isinstance(loop_duration, (int, float)) and float(loop_duration) > 0:
            elapsed = float(elapsed) % float(loop_duration)

    return float(elapsed)
