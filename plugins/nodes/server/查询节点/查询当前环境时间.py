from __future__ import annotations

import time
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询当前环境时间",
    category="查询节点",
    outputs=[("当前环境时间", "浮点数"), ("当前循环天数", "整数")],
    description="查询当前的环境时间，范围为[0,24)",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询当前环境时间(game):
    """查询当前的环境时间，范围为[0,24)"""
    # 约定：本地测试的环境时间基于运行时启动后的 `time.monotonic()` 推进，
    # 且默认以“中午 12:00”作为初始时间，方便图逻辑在演示时出现昼夜差异。
    start = getattr(game, "_ayaya_start_monotonic", None)
    if not isinstance(start, (int, float)):
        start = float(time.monotonic())
        setattr(game, "_ayaya_start_monotonic", float(start))

    base_hour = getattr(game, "_ayaya_env_time_base_hour", None)
    if not isinstance(base_hour, (int, float)):
        base_hour = 12.0
        setattr(game, "_ayaya_env_time_base_hour", float(base_hour))

    elapsed = float(time.monotonic()) - float(start)
    if elapsed < 0:
        elapsed = 0.0

    total_seconds = float(base_hour) * 3600.0 + float(elapsed)
    seconds_per_day = 24.0 * 3600.0

    current_env_time = (float(total_seconds) % seconds_per_day) / 3600.0
    current_day = int(float(total_seconds) // seconds_per_day) + 1
    return float(current_env_time), int(current_day)
