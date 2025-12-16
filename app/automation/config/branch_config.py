# -*- coding: utf-8 -*-
"""
branch_config: 分支输出配置功能
从 editor_connect.py 拆分，提供分支端口添加与分支匹配值配置。

注意：
- 不新增异常捕获；保持与原实现一致的失败返回与日志输出。
- 仅做职责拆分与复用，不改变对外行为与时序。
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Callable, List
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.editor import executor_utils as _exec_utils
from app.automation.editor.executor_protocol import EditorExecutorWithViewport
from app.automation.input import win_input
from app.automation.ports.port_picker import pick_port_center_for_node
from app.automation.vision import invalidate_cache, list_ports as list_ports_for_bbox
from app.automation.config.config_node_steps import (
    handle_regular_param_with_warning,
    handle_regular_param_fallback,
    find_warning_region_for_flow_output,
)
from engine.graph.models.graph_model import GraphModel


def click_add_icon_within_node(
    executor: EditorExecutorWithViewport,
    node_bbox: tuple[int, int, int, int],
    log_callback=None,
    prefer_multi: bool = False,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    *,
    screenshot: Optional[Image.Image] = None,
) -> bool:
    nx, ny, nw, nh = node_bbox

    def _match_add_icon(current_frame: Image.Image):
        local_match = None
        if prefer_multi:
            local_match = editor_capture.match_template(
                current_frame,
                str(executor.node_add_multi_template_path),
                search_region=(int(nx), int(ny), int(nw), int(nh)),
            )
        if not local_match:
            local_match = editor_capture.match_template(
                current_frame,
                str(executor.node_add_template_path),
                search_region=(int(nx), int(ny), int(nw), int(nh)),
            )
        return local_match

    # 无论是否已有截图输入，点击 Add 前都统一执行一次“移出节点到画布空白区域后再截图匹配”的流程。
    # 空白点查找策略：
    # 1. 优先从“节点顶部上方、与节点水平居中对齐”的位置作为起点，在画布区域内寻找安全空白点；
    # 2. 若该方向未能找到合适空白点，则回退到以“节点中心”作为起点的原有策略。
    node_center_editor_x = int(nx + nw // 2)
    node_center_editor_y = int(ny + nh // 2)
    preferred_offset_pixels = max(int(min(nh * 0.8, 80)), 20)
    preferred_top_editor_x = node_center_editor_x
    preferred_top_editor_y = int(ny) - int(preferred_offset_pixels)

    def _find_blank_point_prefer_top() -> Optional[tuple[int, int]]:
        candidate_editor_positions = [
            (int(preferred_top_editor_x), int(preferred_top_editor_y)),
            (int(node_center_editor_x), int(node_center_editor_y)),
        ]
        for editor_x, editor_y in candidate_editor_positions:
            screen_x, screen_y = executor.convert_editor_to_screen_coords(
                int(editor_x),
                int(editor_y),
            )
            snapped = _exec_utils.snap_screen_point_to_canvas_background(
                executor,
                int(screen_x),
                int(screen_y),
                log_callback=log_callback,
                visual_callback=visual_callback,
            )
            if snapped is not None:
                return int(snapped[0]), int(snapped[1])
        return None

    snapped_blank = _find_blank_point_prefer_top()
    if snapped_blank is None:
        executor.log(
            "✗ 未在画布内找到可用空白点（Add重试），放弃本次重试",
            log_callback,
        )
        executor.log(
            "✗ Add 按钮重试前置条件失败：未能在画布上找到安全空白点",
            log_callback,
        )
        return False

    blank_screen_x, blank_screen_y = int(snapped_blank[0]), int(snapped_blank[1])
    executor.log(
        f"[Add重试] 将鼠标移出节点到画布空白位置 screen=({blank_screen_x},{blank_screen_y}) 后重试一次模板匹配",
        log_callback,
    )
    win_input.move_mouse_absolute(int(blank_screen_x), int(blank_screen_y))
    _exec_utils.log_wait_if_needed(
        executor,
        0.1,
        "等待 0.10 秒（鼠标移出节点后重试 Add）",
        log_callback,
    )

    def _capture_and_match() -> tuple[Optional[Image.Image], Any]:
        local_frame = editor_capture.capture_window_strict(executor.window_title)
        if local_frame is None:
            local_frame = editor_capture.capture_window(executor.window_title)
        if not local_frame:
            executor.log("✗ 截图失败（查找Add）", log_callback)
            return None, None
        local_match = _match_add_icon(local_frame)
        if not local_match and visual_callback is not None:
            rects = [
                {
                    "bbox": (int(nx), int(ny), int(nw), int(nh)),
                    "color": (255, 120, 120),
                    "label": "Add搜索区域",
                }
            ]
            visual_callback(local_frame, {"rects": rects})
        return local_frame, local_match

    frame, match = _capture_and_match()
    if not frame or not match:
        executor.log("✗ 未在节点内找到 Add 按钮", log_callback)
        return False

    mx, my, mw, mh, conf = match
    cx = int(mx + mw // 2 + 3)
    cy = int(my + mh // 2)
    sx, sy = executor.convert_editor_to_screen_coords(cx, cy)
    executor.log(f"点击 Add 按钮：窗口坐标({cx},{cy})，置信度={conf:.2f}", log_callback)
    if visual_callback is not None and frame is not None:
        rects = [
            { 'bbox': (int(nx), int(ny), int(nw), int(nh)), 'color': (120, 180, 255), 'label': '节点' },
            { 'bbox': (int(mx), int(my), int(mw), int(mh)), 'color': (255, 180, 0), 'label': f'Add模板 命中{conf:.2f}' }
        ]
        circles = [ { 'center': (int(cx), int(cy)), 'radius': 5, 'color': (0, 220, 0), 'label': '点击' } ]
        visual_callback(frame, { 'rects': rects, 'circles': circles })
    _exec_utils.click_and_verify(executor, sx, sy, "[变参/字典/分支] 点击Add", log_callback)
    _exec_utils.log_wait_if_needed(executor, 0.05, "等待 0.05 秒", log_callback)
    return True


def execute_add_with_icon_clicks(
    executor: EditorExecutorWithViewport,
    node,
    add_count: int,
    *,
    prefer_multi: bool,
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    if add_count <= 0:
        return True

    executor.ensure_program_point_visible(
        node.pos[0],
        node.pos[1],
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
    invalidate_cache()

    def _capture_node_bbox() -> tuple[Optional[Image.Image], tuple[int, int, int, int]]:
        screenshot = editor_capture.capture_window_strict(executor.window_title)
        if screenshot is None:
            screenshot = editor_capture.capture_window(executor.window_title)
        if not screenshot:
            executor.log("✗ 截图失败（Add 流程）", log_callback)
            return None, (0, 0, 0, 0)
        node_bbox = executor.find_best_node_bbox(screenshot, node.title, node.pos)
        if node_bbox[2] <= 0:
            executor.log("✗ 未能定位目标节点（Add 流程）", log_callback)
            return None, (0, 0, 0, 0)
        if visual_callback is not None:
            rects = [
                {
                    'bbox': (int(node_bbox[0]), int(node_bbox[1]), int(node_bbox[2]), int(node_bbox[3])),
                    'color': (120, 200, 255),
                    'label': f"目标节点: {node.title}",
                }
            ]
            visual_callback(screenshot, { 'rects': rects })
        return screenshot, node_bbox

    screenshot, node_bbox = _capture_node_bbox()
    if not screenshot:
        return False

    for _ in range(add_count):
        if pause_hook is not None:
            pause_hook()
        if allow_continue is not None and not allow_continue():
            executor.log("用户终止/暂停，放弃添加端口", log_callback)
            return False
        ok = click_add_icon_within_node(
            executor,
            node_bbox,
            log_callback,
            prefer_multi=prefer_multi,
            visual_callback=visual_callback,
            screenshot=screenshot,
        )
        if not ok:
            return False
        _exec_utils.log_wait_if_needed(executor, 0.5, "等待 0.50 秒", log_callback)
        invalidate_cache()
        screenshot, node_bbox = _capture_node_bbox()
        if not screenshot:
            return False
    return True


def execute_add_branch_outputs(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    node_id = todo_item.get("node_id")
    add_count = int(todo_item.get("add_count") or 0)
    if not node_id or node_id not in graph_model.nodes:
        executor.log("✗ 分支端口添加缺少节点或节点不存在", log_callback)
        return False
    if add_count <= 0:
        return True
    node = graph_model.nodes[node_id]
    return execute_add_with_icon_clicks(
        executor,
        node,
        add_count,
        prefer_multi=True,
        graph_model=graph_model,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
    )


def execute_config_branch_outputs(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    """为多分支节点的流程输出端口输入匹配值（点击 Warning 后输入）。

    参考 execute_config_node_merged，但目标为右侧"流程输出口"。
    """
    node_id = todo_item.get("node_id")
    branches = todo_item.get("branches") or []
    if not node_id or node_id not in graph_model.nodes:
        executor.log("✗ 分支输出配置缺少节点或节点不存在", log_callback)
        return False
    if not isinstance(branches, list) or len(branches) == 0:
        return True
    node = graph_model.nodes[node_id]

    # 多分支节点始终包含一个“默认”流程输出端口，该端口作为第一个输出口存在，
    # 但在配置分支输出步骤中不需要也不应该被写入匹配值。
    # 因此在按序号回退时，需要整体跳过该默认端口，从第二个输出端口开始对应分支列表。
    output_ports = list(getattr(node, "outputs", []) or [])
    has_default_output_port = any(
        isinstance(getattr(port_obj, "name", None), str)
        and str(getattr(port_obj, "name")).strip() == "默认"
        for port_obj in output_ports
    )
    ordinal_offset_for_branches = 1 if has_default_output_port else 0
    executor.ensure_program_point_visible(
        node.pos[0],
        node.pos[1],
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
    def _capture_node_context() -> tuple[Optional[Image.Image], tuple[int, int, int, int], List]:
        screenshot = editor_capture.capture_window_strict(executor.window_title)
        if screenshot is None:
            screenshot = editor_capture.capture_window(executor.window_title)
        if not screenshot:
            executor.log("✗ 截图失败（分支输出配置）", log_callback)
            return None, (0, 0, 0, 0), []
        node_bbox = executor.find_best_node_bbox(screenshot, node.title, node.pos)
        if node_bbox[2] <= 0:
            executor.log("✗ 未能定位目标节点（分支输出配置）", log_callback)
            return None, (0, 0, 0, 0), []
        ports_snapshot = list_ports_for_bbox(screenshot, node_bbox)
        return screenshot, node_bbox, ports_snapshot

    screenshot, node_bbox, ports_snapshot = _capture_node_context()
    if not screenshot:
        return False
    if visual_callback is not None:
        rects = [ { 'bbox': (int(node_bbox[0]), int(node_bbox[1]), int(node_bbox[2]), int(node_bbox[3])), 'color': (120, 200, 255), 'label': f"目标节点: {node.title}" } ]
        visual_callback(screenshot, { 'rects': rects })

    # 逐一设置每个分支端口
    for branch_index, item in enumerate(branches):
        if pause_hook is not None:
            pause_hook()
        if allow_continue is not None and not allow_continue():
            executor.log("用户终止/暂停，放弃分支输出配置", log_callback)
            return False
        port_name = str(item.get("port_name") or item.get("name") or "")
        value_text = str(item.get("value") or port_name)
        if not port_name:
            continue
        # 定位端口中心（输出侧）
        ordinal_index_value = int(branch_index) + int(ordinal_offset_for_branches)
        port_center = pick_port_center_for_node(
            executor,
            screenshot,
            node_bbox,
            port_name,
            want_output=True,
            expected_kind="flow",
            log_callback=log_callback,
            ordinal_fallback_index=ordinal_index_value,
            ports_list=ports_snapshot,
            list_ports_for_bbox_func=list_ports_for_bbox,
        )
        if port_center == (0, 0):
            executor.log(f"✗ 未能定位分支输出端口: {port_name}", log_callback)
            return False
        region_info = find_warning_region_for_flow_output(
            executor,
            screenshot,
            node_bbox,
            port_center,
            port_name,
            log_callback,
            ports_snapshot=ports_snapshot,
        )
        if region_info is None:
            return False
        search_region, cur_port, _next_port = region_info

        hit_warning = handle_regular_param_with_warning(
            executor,
            screenshot,
            search_region,
            value_text,
            pause_hook,
            allow_continue,
            log_callback,
            visual_callback,
            log_prefix="[分支配置]",
        )
        if not hit_warning:
            ok_fallback = handle_regular_param_fallback(
                executor,
                port_center,
                value_text,
                "flow",
                node_bbox,
                cur_port,
                pause_hook,
                allow_continue,
                log_callback,
                visual_callback,
                fallback_click_offset=(-50, 25),
                log_prefix="[分支配置]",
            )
            if not ok_fallback:
                return False
        _exec_utils.log_wait_if_needed(executor, 0.1, "等待 0.10 秒", log_callback)
    return True

