from __future__ import annotations

import time
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询游戏已进行时间",
    category="查询节点",
    outputs=[("游戏已进行时间", "整数")],
    description="查询游戏已进行了多长时间，单位秒",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询游戏已进行时间(game):
    """查询游戏已进行了多长时间，单位秒"""
    start = getattr(game, "_ayaya_start_monotonic", None)
    if not isinstance(start, (int, float)):
        start = float(time.monotonic())
        setattr(game, "_ayaya_start_monotonic", float(start))

    elapsed = float(time.monotonic()) - float(start)
    if elapsed < 0:
        elapsed = 0.0
    return int(elapsed)
