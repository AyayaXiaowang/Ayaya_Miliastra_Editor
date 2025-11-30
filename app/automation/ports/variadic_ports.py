# -*- coding: utf-8 -*-
"""
variadic_ports: 为节点添加变参输入端口。

注意：
- 不新增异常捕获；保持与原实现一致的失败返回与日志输出。
- 仅做职责拆分与复用，不改变对外行为与时序。
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Callable
import re
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.core.executor_protocol import EditorExecutorWithViewport
from app.automation.config.branch_config import execute_add_with_icon_clicks
from app.automation.ports._add_ports_common import resolve_node_and_initial_add_count
from engine.graph.models.graph_model import GraphModel


def execute_add_variadic_inputs(
    executor: EditorExecutorWithViewport,
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
        feature_label="变参端口添加",
        log_callback=log_callback,
    )
    if node_model is None:
        return False
    executor.ensure_program_point_visible(
        node_model.pos[0],
        node_model.pos[1],
        margin_ratio=0.10,
        max_steps=8,
        pan_step_pixels=420,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
        graph_model=graph_model,
        force_pan_if_inside_margin=False,
    )
    if add_count <= 0:
        desired_total = 0
        values = todo_item.get("values") or todo_item.get("items")
        target_count_field = todo_item.get("target_count") or todo_item.get("target_total")
        if isinstance(target_count_field, int):
            desired_total = int(target_count_field)
        elif isinstance(values, (list, tuple)):
            desired_total = int(len(values))
        if desired_total > 0:
            from app.automation.vision import list_ports as list_ports_for_bbox
            screenshot = editor_capture.capture_window(executor.window_title)
            if not screenshot:
                executor._log("✗ 截图失败（统计变参端口）", log_callback)
                return False
            node_bbox = executor._find_best_node_bbox(screenshot, node_model.title, node_model.pos)
            if node_bbox[2] <= 0:
                executor._log("✗ 未能定位目标节点（统计变参端口）", log_callback)
                return False
            ports_now = list_ports_for_bbox(screenshot, node_bbox)
            current_numeric_inputs = [
                port
                for port in ports_now
                if port.side == "left"
                and isinstance(port.name_cn, str)
                and re.match(r"^\d+$", port.name_cn) is not None
            ]
            cur_count = int(len(current_numeric_inputs))
            add_count = max(0, desired_total - cur_count)
            executor._log(f"· 变参端口：当前{cur_count}，目标{desired_total}，计划新增{add_count}", log_callback)
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

