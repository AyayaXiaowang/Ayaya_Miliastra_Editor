# -*- coding: utf-8 -*-
"""
dict_ports: 为节点添加字典键值对端口。

注意：
- 不新增异常捕获；保持与原实现一致的失败返回与日志输出。
- 仅做职责拆分与复用，不改变对外行为与时序。
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Callable
from PIL import Image

from app.automation.config.branch_config import execute_add_with_icon_clicks
from app.automation.ports._add_ports_common import resolve_node_and_initial_add_count
from engine.graph.models.graph_model import GraphModel


def execute_add_dict_pairs(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    node_model, add_count = resolve_node_and_initial_add_count(
        executor,
        todo_item,
        graph_model,
        feature_label="字典端口添加",
        log_callback=log_callback,
    )
    if node_model is None:
        return False
    if add_count <= 0:
        return True
    return execute_add_with_icon_clicks(
        executor,
        node_model,
        add_count,
        prefer_multi=False,
        graph_model=graph_model,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
    )

