# -*- coding: utf-8 -*-
"""
坐标与视口相关能力：
- 程序↔编辑器↔屏幕 坐标换算
- 基于锚点的坐标校准与视口定位
- 视口对齐（右键拖拽 + 相位相关纠偏）
- 程序侧视口矩形计算与“同屏连线”判定
"""

from typing import Optional, Tuple, Dict, Any, Callable, List
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.input.common import (
    DEFAULT_DRAG_MOUSE_UP_MS,
    compute_position_thresholds,
    sleep_seconds,
)
from app.automation.vision import list_nodes, invalidate_cache
from app.automation.core.view_alignment import run_pan_loop, PanEvaluation
from app.automation.core.view_mapping import (
    compute_clamped_step,
    perform_drag_with_motion_estimation,
)
from app.automation.core.ui_constants import (
    NODE_VIEW_WIDTH_PX,
    NODE_VIEW_HEIGHT_PX,
    VIEW_SAFE_MARGIN_RATIO_DEFAULT,
    VIEW_MAX_PAN_STEPS_DEFAULT,
    VIEW_PAN_STEP_PX_DEFAULT,
    ANCHOR_CREATION_FIRST_WAIT_SECONDS,
    ANCHOR_CREATION_POST_SELECT_WAIT_SECONDS,
    OCR_CACHE_FLUSH_WAIT_SECONDS,
)
from engine.graph.models.graph_model import GraphModel, NodeModel
from app.automation.core import editor_nodes
from app.automation.core import executor_utils as _exec_utils

MIN_SCALE_RATIO = 1e-6
FIXED_SCALE_RATIO = 1.0


def _get_valid_scale_ratio(executor) -> float:
    if executor.scale_ratio is None:
        raise ValueError("坐标未校准，请先调用calibrate_coordinates()")
    scale = float(executor.scale_ratio)
    if abs(scale) <= MIN_SCALE_RATIO:
        raise ValueError("缩放比例异常（为0或接近0），请重新执行坐标校准")
    return scale


def convert_program_to_editor_coords(executor, program_x: float, program_y: float) -> Tuple[int, int]:
    scale = _get_valid_scale_ratio(executor)
    if executor.origin_node_pos is None:
        raise ValueError("坐标未校准，请先调用calibrate_coordinates()")

    offset_x = program_x * scale
    offset_y = program_y * scale
    editor_x = int(executor.origin_node_pos[0] + offset_x)
    editor_y = int(executor.origin_node_pos[1] + offset_y)
    return (editor_x, editor_y)


def convert_editor_to_screen_coords(executor, editor_x: int, editor_y: int) -> Tuple[int, int]:
    window_rect = editor_capture.get_window_rect(executor.window_title)
    if not window_rect:
        raise ValueError("未找到编辑器窗口")
    window_left, window_top, _, _ = window_rect
    screen_x = window_left + editor_x
    screen_y = window_top + editor_y
    return (screen_x, screen_y)


def get_program_viewport_rect(executor) -> Tuple[float, float, float, float]:
    scale = _get_valid_scale_ratio(executor)
    if executor.origin_node_pos is None:
        raise ValueError("坐标未校准，无法计算程序视口矩形")

    screenshot = editor_capture.capture_window(executor.window_title)
    if not screenshot:
        raise ValueError("截图失败，无法计算程序视口矩形")

    rx, ry, rw, rh = editor_capture.get_region_rect(screenshot, "节点图布置区域")

    left_prog = (float(rx) - float(executor.origin_node_pos[0])) / scale
    top_prog = (float(ry) - float(executor.origin_node_pos[1])) / scale
    width_prog = float(rw) / scale
    height_prog = float(rh) / scale

    return (float(left_prog), float(top_prog), float(width_prog), float(height_prog))


def will_connect_too_far(executor, graph_model: GraphModel, src_node_id: str, dst_node_id: str, margin_ratio: float = VIEW_SAFE_MARGIN_RATIO_DEFAULT) -> tuple[bool, str]:
    if executor.scale_ratio is None or executor.origin_node_pos is None:
        return (False, "未校准，跳过距离判定")
    scale = float(executor.scale_ratio)
    if abs(scale) <= MIN_SCALE_RATIO:
        return (False, "缩放比例异常（为0或过小），跳过距离判定")
    if src_node_id not in graph_model.nodes or dst_node_id not in graph_model.nodes:
        return (False, "节点缺失，跳过距离判定")
    screenshot = editor_capture.capture_window(executor.window_title)
    if not screenshot:
        return (False, "截图失败，跳过距离判定")
    rx, ry, rw, rh = editor_capture.get_region_rect(screenshot, "节点图布置区域")
    safe_w = int(float(rw) * (1.0 - 2.0 * float(margin_ratio)))
    safe_h = int(float(rh) * (1.0 - 2.0 * float(margin_ratio)))

    src = graph_model.nodes[src_node_id]
    dst = graph_model.nodes[dst_node_id]
    sx, sy = convert_program_to_editor_coords(executor, float(src.pos[0]), float(src.pos[1]))
    dx, dy = convert_program_to_editor_coords(executor, float(dst.pos[0]), float(dst.pos[1]))

    node_w = int(NODE_VIEW_WIDTH_PX * scale)
    node_h = int(NODE_VIEW_HEIGHT_PX * scale)
    left = int(min(sx, dx))
    top = int(min(sy, dy))
    right = int(max(sx + node_w, dx + node_w))
    bottom = int(max(sy + node_h, dy + node_h))
    bbox_w = int(right - left)
    bbox_h = int(bottom - top)

    too_far_w = bool(bbox_w > safe_w)
    too_far_h = bool(bbox_h > safe_h)
    too_far = bool(too_far_w or too_far_h)

    reason = (
        f"两端点同屏检查：bbox={bbox_w}x{bbox_h} 安全区={safe_w}x{safe_h}，"
        + ("宽度超出" if too_far_w else "")
        + ("/" if (too_far_w and too_far_h) else "")
        + ("高度超出" if too_far_h else "")
    )
    return (too_far, reason)


def ensure_program_point_visible(
    executor,
    program_x: float,
    program_y: float,
    margin_ratio: float = VIEW_SAFE_MARGIN_RATIO_DEFAULT,
    max_steps: int = VIEW_MAX_PAN_STEPS_DEFAULT,
    pan_step_pixels: int = VIEW_PAN_STEP_PX_DEFAULT,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    graph_model: Optional[GraphModel] = None,
    force_pan_if_inside_margin: bool = False,
) -> None:
    scale = _get_valid_scale_ratio(executor)
    if executor.origin_node_pos is None:
        raise ValueError("坐标未校准，请先调用calibrate_coordinates()")

    if allow_continue is not None and not allow_continue():
        executor.log("用户终止/暂停，放弃视口对齐", log_callback)
        return

    force_when_inside = bool(force_pan_if_inside_margin)
    step_counter: Dict[str, int] = {"count": -1}

    def _capture_frame() -> Image.Image:
        frame: Image.Image | None = None

        # 优先：在视口未变化且执行器开启场景缓存优化时，复用场景快照中的截图，
        # 避免在连续参数配置/类型设置步骤中为视口对齐重复整帧截图。
        get_scene_snapshot = getattr(executor, "get_scene_snapshot", None)
        if callable(get_scene_snapshot) and bool(
            getattr(executor, "enable_scene_snapshot_optimization", True)
        ):
            scene_snapshot = get_scene_snapshot()
            can_reuse = getattr(scene_snapshot, "can_reuse_for_current_view", None)
            if callable(can_reuse) and bool(can_reuse()):
                cached = getattr(scene_snapshot, "screenshot", None)
                if cached is not None:
                    frame = cached

        if frame is None:
            frame = editor_capture.capture_window(executor.window_title)
        if frame is None:
            raise ValueError("截图失败")
        return frame

    def _evaluate(current_image: Image.Image, step_index: int) -> PanEvaluation:
        step_counter["count"] = int(step_index)
        if pause_hook is not None:
            pause_hook()
        if allow_continue is not None and not allow_continue():
            executor.log("用户终止/暂停，放弃视口对齐", log_callback)
            return PanEvaluation(satisfied=False, drag_args=None, aborted=True)

        editor_x, editor_y = convert_program_to_editor_coords(executor, program_x, program_y)
        region_x, region_y, region_w, region_h = editor_capture.get_region_rect(current_image, "节点图布置区域")
        safe_left = int(region_x + region_w * margin_ratio)
        safe_right = int(region_x + region_w * (1.0 - margin_ratio))
        safe_top = int(region_y + region_h * margin_ratio)
        safe_bottom = int(region_y + region_h * (1.0 - margin_ratio))

        executor.log(
            f"[视口对齐] 目标程序=({program_x:.1f},{program_y:.1f}) 预期editor=({editor_x},{editor_y}) 安全区x=[{safe_left},{safe_right}] y=[{safe_top},{safe_bottom}]",
            log_callback,
        )

        rects = [
            {
                "bbox": (int(safe_left), int(safe_top), int(safe_right - safe_left), int(safe_bottom - safe_top)),
                "color": (0, 200, 255),
                "label": "安全区",
            }
        ]
        circles = [
            {"center": (int(editor_x), int(editor_y)), "radius": 6, "color": (255, 200, 0), "label": "目标点"}
        ]
        executor.emit_visual(current_image, {"rects": rects, "circles": circles}, visual_callback)

        inside_safe = bool(safe_left <= editor_x <= safe_right and safe_top <= editor_y <= safe_bottom)
        if inside_safe:
            if not force_when_inside:
                executor.log(
                    "[视口对齐] 目标点已在安全区内，本次不执行拖拽",
                    log_callback,
                )
                return PanEvaluation(satisfied=True)
            if step_index > 0:
                executor.log(
                    "[视口对齐] 目标点已回到安全区内，结束额外拖拽",
                    log_callback,
                )
                return PanEvaluation(satisfied=True)
            executor.log(
                "[视口对齐] 目标点已在安全区内，根据请求执行一次额外拖拽以靠近中心",
                log_callback,
            )

        center_x = int(region_x + region_w // 2)
        center_y = int(region_y + region_h // 2)
        vector_x = int(editor_x - center_x)
        vector_y = int(editor_y - center_y)
        step_x, step_y = compute_clamped_step(vector_x, vector_y, pan_step_pixels)

        start_editor_x = center_x
        start_editor_y = center_y
        end_editor_x = center_x - int(step_x)
        end_editor_y = center_y - int(step_y)

        start_screen_x, start_screen_y = convert_editor_to_screen_coords(executor, start_editor_x, start_editor_y)
        end_screen_x, end_screen_y = convert_editor_to_screen_coords(executor, end_editor_x, end_editor_y)

        executor.log(
            f"[视口对齐] 右键拖拽: start(editor)=({start_editor_x},{start_editor_y}) -> end(editor)=({end_editor_x},{end_editor_y}) 步长=({step_x},{step_y})",
            log_callback,
        )

        drag_plan = {
            "start_screen": (int(start_screen_x), int(start_screen_y)),
            "end_screen": (int(end_screen_x), int(end_screen_y)),
            "roi": (int(region_x), int(region_y), int(region_w), int(region_h)),
            # 记录期望的“内容位移”（编辑器坐标系下），方向需与相位相关得到的 Δ 一致。
            # 对于内容移动而言，拖拽向量与内容位移方向相反，因此这里使用 (-step_x, -step_y)。
            "expected_content_delta": (int(-step_x), int(-step_y)),
        }
        return PanEvaluation(satisfied=False, drag_args=drag_plan)

    def _execute_drag(current_image: Image.Image, plan: Dict[str, Any]) -> Image.Image:
        start_screen_x, start_screen_y = plan["start_screen"]
        end_screen_x, end_screen_y = plan["end_screen"]
        roi = plan["roi"]

        # 将拖拽起点吸附到画布背景上，避免从节点矩形内部发起无效拖拽
        snapped = _exec_utils.snap_screen_point_to_canvas_background(
            executor,
            int(start_screen_x),
            int(start_screen_y),
            log_callback=log_callback,
            visual_callback=visual_callback,
        )
        if snapped is None:
            # 若无法找到安全的画布背景点，则本次拖拽放弃，避免在节点矩形上发起无效拖拽。
            executor.log(
                "[视口对齐] 无法在画布内为拖拽起点找到安全背景色位置，本次拖拽已放弃",
                log_callback,
            )
            return current_image

        drag_start_x = int(snapped[0])
        drag_start_y = int(snapped[1])

        # 限制拖拽起点和终点都在编辑器窗口矩形内，避免光标跑出程序窗口
        win_rect = editor_capture.get_window_rect(executor.window_title)
        if win_rect is not None:
            win_left, win_top, win_right, win_bottom = win_rect

            # 记录“规划起点/终点”与“吸附后起点”的 editor 坐标，方便在日志与监控面板中对齐
            orig_start_editor_x = int(start_screen_x) - int(win_left)
            orig_start_editor_y = int(start_screen_y) - int(win_top)
            snapped_start_editor_x = int(drag_start_x) - int(win_left)
            snapped_start_editor_y = int(drag_start_y) - int(win_top)
            planned_end_editor_x = int(end_screen_x) - int(win_left)
            planned_end_editor_y = int(end_screen_y) - int(win_top)
            executor.log(
                "[视口对齐] 拖拽起点吸附: 规划editor="
                f"({int(orig_start_editor_x)},{int(orig_start_editor_y)}) → "
                f"吸附后editor=({int(snapped_start_editor_x)},{int(snapped_start_editor_y)})，"
                f"终点editor=({int(planned_end_editor_x)},{int(planned_end_editor_y)})",
                log_callback,
            )

            def _clamp_screen_point(x: int, y: int) -> tuple[int, int]:
                clamped_x = x
                clamped_y = y
                if clamped_x < int(win_left):
                    clamped_x = int(win_left)
                elif clamped_x >= int(win_right):
                    clamped_x = int(win_right) - 1
                if clamped_y < int(win_top):
                    clamped_y = int(win_top)
                elif clamped_y >= int(win_bottom):
                    clamped_y = int(win_bottom) - 1
                return (int(clamped_x), int(clamped_y))

            drag_start_x, drag_start_y = _clamp_screen_point(drag_start_x, drag_start_y)
            end_screen_x, end_screen_y = _clamp_screen_point(int(end_screen_x), int(end_screen_y))

        def _drag_action() -> None:
            # 在真正执行拖拽前，将“拖拽起点/终点”以可视化方式叠加到当前截图上，便于在监控面板中区分各个关键点
            if callable(getattr(executor, "emit_visual", None)):
                win_rect_local = editor_capture.get_window_rect(executor.window_title)
                rects_drag = []
                circles_drag = []
                if win_rect_local is not None:
                    win_left_local, win_top_local, _win_right_local, _win_bottom_local = win_rect_local
                    pre_start_editor_x = int(start_screen_x) - int(win_left_local)
                    pre_start_editor_y = int(start_screen_y) - int(win_top_local)
                    snapped_start_editor_x2 = int(drag_start_x) - int(win_left_local)
                    snapped_start_editor_y2 = int(drag_start_y) - int(win_top_local)
                    end_editor_x = int(end_screen_x) - int(win_left_local)
                    end_editor_y = int(end_screen_y) - int(win_top_local)
                    circles_drag.append(
                        {
                            "center": (int(pre_start_editor_x), int(pre_start_editor_y)),
                            "radius": 6,
                            "color": (255, 220, 0),
                            "label": "预选拖拽起点",
                        }
                    )
                    circles_drag.append(
                        {
                            "center": (int(snapped_start_editor_x2), int(snapped_start_editor_y2)),
                            "radius": 7,
                            "color": (255, 80, 80),
                            "label": "吸附拖拽起点",
                        }
                    )
                    circles_drag.append(
                        {
                            "center": (int(end_editor_x), int(end_editor_y)),
                            "radius": 6,
                            "color": (80, 220, 80),
                            "label": "拖拽终点",
                        }
                    )
                executor.emit_visual(current_image, {"rects": rects_drag, "circles": circles_drag}, visual_callback)
            editor_capture.drag_right_button(drag_start_x, drag_start_y, end_screen_x, end_screen_y)
            invalidate_cache()
            sleep_seconds(DEFAULT_DRAG_MOUSE_UP_MS / 1000.0)

        after, dx_corr, dy_corr = perform_drag_with_motion_estimation(
            current_image,
            drag_action=_drag_action,
            capture_after=lambda: editor_capture.capture_window(executor.window_title),
            roi=roi,
        )
        # 当相位相关给出的位移为 (0,0) 而理论拖拽步长较大时，
        # 说明当前 ROI 内可能缺乏明显纹理（例如已拖入大面积空白区域），
        # 此时允许回退到基于拖拽向量的“预期内容位移”，避免坐标映射长期停滞。
        effective_dx = dx_corr
        effective_dy = dy_corr
        expected_delta = plan.get("expected_content_delta")
        if expected_delta is not None:
            expected_dx, expected_dy = expected_delta
            # 仅在估计结果完全为 0 且预期步长足够大时启用回退，避免过度干预正常的相位相关结果。
            if dx_corr == 0 and dy_corr == 0 and (
                (expected_dx != 0) or (expected_dy != 0)
            ):
                effective_dx = int(expected_dx)
                effective_dy = int(expected_dy)
                executor.log(
                    f"[视口对齐] 内容位移估计为 0，回退使用预期拖拽位移 Δ≈({effective_dx},{effective_dy}) 更新原点映射",
                    log_callback,
                )
        executor.origin_node_pos = (
            int(executor.origin_node_pos[0] + effective_dx),
            int(executor.origin_node_pos[1] + effective_dy),
        )
        executor.log(
            f"[视口对齐] 内容位移估计 Δ=({dx_corr},{dy_corr})，实际应用偏移 Δ=({effective_dx},{effective_dy})，已据此更新原点映射",
            log_callback,
        )
        if hasattr(executor, "mark_view_changed"):
            executor.mark_view_changed("pan")
        return after

    outcome = run_pan_loop(
        _capture_frame,
        _evaluate,
        _execute_drag,
        max_steps=max_steps,
    )

    steps_used = 0
    if step_counter["count"] >= 0:
        steps_used = int(step_counter["count"]) + 1

    if outcome.aborted:
        executor.log(
            f"[视口对齐] 对齐循环中止（steps≈{steps_used}）",
            log_callback,
        )
        return

    if outcome.success:
        executor.log(
            f"[视口对齐] 对齐完成（steps≈{steps_used}）",
            log_callback,
        )
    else:
        executor.log(
            f"[视口对齐] 达到最大步数仍未将目标移入安全区（steps={max_steps}），请检查坐标映射或画布边界",
            log_callback,
        )
    return


def calibrate_coordinates(
    executor,
    anchor_node_title: str,
    anchor_program_pos: Tuple[float, float],
    log_callback=None,
    create_anchor_node: bool = True,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    graph_model: Optional[GraphModel] = None,
) -> bool:
    executor.log("开始锚点坐标校准/视口定位(使用首节点作为锚点)...", log_callback)

    window_rect = editor_capture.get_window_rect(executor.window_title)
    if not window_rect:
        executor.log("✗ 未找到编辑器窗口", log_callback)
        return False
    window_left, window_top, window_right, window_bottom = window_rect
    window_width = window_right - window_left
    window_height = window_bottom - window_top
    executor.log(f"✓ 找到编辑器窗口: {window_width}x{window_height}", log_callback)

    screenshot = editor_capture.capture_window(executor.window_title)
    if not screenshot:
        executor.log("✗ 截图失败", log_callback)
        return False

    region_rect = editor_capture.get_region_rect(screenshot, "节点图布置区域")
    region_x, region_y, region_width, region_height = region_rect

    offset_x = int(region_width * 0.01)
    offset_y = int(region_height * 0.01)
    click_pos_x = region_x + offset_x
    click_pos_y = region_y + offset_y
    screen_x, screen_y = convert_editor_to_screen_coords(executor, click_pos_x, click_pos_y)
    rects = [ { 'bbox': (int(region_x), int(region_y), int(region_width), int(region_height)), 'color': (120, 200, 255), 'label': '节点图布置区域' } ]
    circles = [ { 'center': (int(click_pos_x), int(click_pos_y)), 'radius': 6, 'color': (0, 220, 0), 'label': '锚点点击' } ]
    executor.emit_visual(screenshot, { 'rects': rects, 'circles': circles }, visual_callback)

    if create_anchor_node:
        executor.log(f"准备在 ({screen_x}, {screen_y}) 创建锚点节点 '{anchor_node_title}'...", log_callback)
        executor.set_last_context_click_editor_pos(click_pos_x, click_pos_y)
        if pause_hook is not None:
            pause_hook()
        if allow_continue is not None and not allow_continue():
            executor.log("用户终止/暂停，放弃坐标校准", log_callback)
            return False
        if not _exec_utils.right_click_with_hooks(executor, screen_x, screen_y, pause_hook, allow_continue, log_callback, visual_callback):
            return False
        executor.log(f"等待 {ANCHOR_CREATION_FIRST_WAIT_SECONDS:.2f} 秒", log_callback)
        sleep_seconds(ANCHOR_CREATION_FIRST_WAIT_SECONDS)
        if not _exec_utils.input_text_with_hooks(executor, anchor_node_title, pause_hook, allow_continue, log_callback):
            return False
        wait_seconds = getattr(editor_nodes, "POST_INPUT_STABILIZE_SECONDS", 1.5)
        if not executor.wait_with_hooks(wait_seconds, pause_hook, allow_continue, 0.1, log_callback):
            return False
        executor.log("初始化OCR引擎...", log_callback)
        editor_capture.get_ocr_engine()
        executor.log(f"等待候选列表并点击 '{anchor_node_title}'...", log_callback)
        if not editor_nodes.select_from_search_popup(
            executor,
            anchor_node_title,
            wait_seconds=3.0,
            log_callback=log_callback,
            exclude_top_pixels=None,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            visual_callback=visual_callback,
        ):
            executor.log(f"✗ 未能选择 '{anchor_node_title}'，终止校准", log_callback)
            return False
        executor.log(f"等待 {ANCHOR_CREATION_POST_SELECT_WAIT_SECONDS:.2f} 秒", log_callback)
        sleep_seconds(ANCHOR_CREATION_POST_SELECT_WAIT_SECONDS)
        invalidate_cache()
        executor.log(f"刷新识别缓存并等待 {OCR_CACHE_FLUSH_WAIT_SECONDS:.2f} 秒", log_callback)
        sleep_seconds(OCR_CACHE_FLUSH_WAIT_SECONDS)
    else:
        executor.set_last_context_click_editor_pos(click_pos_x, click_pos_y)

    executor.log("等待锚点节点出现(最多8秒)... [方法: 视觉识别(list_nodes)]", log_callback)
    screenshot2, candidates = executor.poll_node_candidates(
        anchor_node_title,
        8.0,
        log_callback,
        pause_hook,
        allow_continue,
    )
    if not candidates or screenshot2 is None:
        executor.log("✗ 未找到锚点节点（视觉识别未命中）", log_callback)
        return False
    target_cn = executor.extract_chinese(anchor_node_title)
    rel_x = rel_y = match_w = match_h = rel_cx = rel_cy = 0

    # 使用锚点截图更新场景快照与识别缓存，避免后续步骤在校准后仍引用旧画面
    detected_nodes = list_nodes(screenshot2)
    get_scene_snapshot = getattr(executor, "get_scene_snapshot", None)
    if callable(get_scene_snapshot) and bool(
        getattr(executor, "enable_scene_snapshot_optimization", True)
    ):
        scene_snapshot = get_scene_snapshot()
        update_method = getattr(scene_snapshot, "update_from_detection", None)
        if callable(update_method):
            executor.log(
                f"[锚点校准] 使用当前截图更新场景快照：检测节点={len(detected_nodes)}",
                log_callback,
            )
            update_method(screenshot2, detected_nodes)

    if len(candidates) == 1 and graph_model is None:
        rel_x, rel_y, match_w, match_h, rel_cx, rel_cy = candidates[0]
    else:
        if graph_model is not None and len(candidates) > 1:
            name_to_detections: dict[str, list[Tuple[int, int, int, int]]] = {}
            for nd in detected_nodes:
                det_cn = executor.extract_chinese(getattr(nd, "name_cn", "") or "")
                if not det_cn:
                    continue
                bucket = name_to_detections.get(det_cn, [])
                bx, by, bw, bh = nd.bbox
                bucket.append((int(bx), int(by), int(bw), int(bh)))
                name_to_detections[det_cn] = bucket

            def _score_candidate(cand: Tuple[int, int, int, int, int, int]) -> Tuple[int, float]:
                cx0, cy0, w0, h0 = int(cand[0]), int(cand[1]), int(cand[2]), int(cand[3])
                scale_est = (float(w0) / NODE_VIEW_WIDTH_PX + float(h0) / NODE_VIEW_HEIGHT_PX) * 0.5
                anchor_prog_x = float(anchor_program_pos[0])
                anchor_prog_y = float(anchor_program_pos[1])
                origin_x_est = float(cx0) - anchor_prog_x * scale_est
                origin_y_est = float(cy0) - anchor_prog_y * scale_est
                neighbors: list[Tuple[float, NodeModel]] = []
                for node in graph_model.nodes.values():
                    if (
                        executor.extract_chinese(node.title) == target_cn
                        and node.pos[0] == anchor_program_pos[0]
                        and node.pos[1] == anchor_program_pos[1]
                    ):
                        continue
                    dxp = float(node.pos[0] - anchor_program_pos[0])
                    dyp = float(node.pos[1] - anchor_program_pos[1])
                    dist2p = dxp * dxp + dyp * dyp
                    neighbors.append((dist2p, node))
                neighbors.sort(key=lambda t: t[0])
                neighbors = neighbors[:8]
                matches = 0
                total_err = 0.0
                pos_threshold_x, pos_threshold_y = compute_position_thresholds(float(scale_est))
                for _dist2, nb in neighbors:
                    nb_cn = executor.extract_chinese(nb.title)
                    det_list = name_to_detections.get(nb_cn, [])
                    if not det_list:
                        continue
                    exp_x = origin_x_est + float(nb.pos[0]) * scale_est
                    exp_y = origin_y_est + float(nb.pos[1]) * scale_est
                    best_local_err = 1e18
                    for dbx, dby, dbw, dbh in det_list:
                        dx = float(dbx) - float(exp_x)
                        dy = float(dby) - float(exp_y)
                        if abs(dx) <= pos_threshold_x and abs(dy) <= pos_threshold_y:
                            err2 = dx * dx + dy * dy
                            if err2 < best_local_err:
                                best_local_err = err2
                    if best_local_err < 1e18:
                        matches += 1
                        total_err += best_local_err
                return matches, -float(total_err)

            best_score = (-1, float("-inf"))
            best_idx = 0
            for idx, cand in enumerate(candidates):
                score = _score_candidate(cand)
                if score > best_score:
                    best_score = score
                    best_idx = idx
            rel_x, rel_y, match_w, match_h, rel_cx, rel_cy = candidates[best_idx]
        else:
            last_click_pos = executor.get_last_context_click_editor_pos()
            if last_click_pos is not None and len(candidates) > 1:
                px, py = last_click_pos
                rel_x, rel_y, match_w, match_h, rel_cx, rel_cy = min(
                    candidates,
                    key=lambda cand: (float(cand[0] - int(px)) ** 2 + float(cand[1] - int(py)) ** 2),
                )
            else:
                rel_x, rel_y, match_w, match_h, rel_cx, rel_cy = candidates[0]
    match_x, match_y = convert_editor_to_screen_coords(executor, rel_x, rel_y)
    executor.log(f"✓ 找到锚点节点: 窗口内位置({rel_x}, {rel_y}), 尺寸({match_w}x{match_h})", log_callback)
    screenshot2 = editor_capture.capture_window(executor.window_title)
    if screenshot2:
        rects_anchor = [ { 'bbox': (int(rel_x), int(rel_y), int(match_w), int(match_h)), 'color': (255, 120, 120), 'label': '锚点节点' } ]
        executor.emit_visual(screenshot2, { 'rects': rects_anchor }, visual_callback)

    program_node_width = NODE_VIEW_WIDTH_PX
    program_node_height = NODE_VIEW_HEIGHT_PX
    scale_x = float(match_w) / program_node_width
    scale_y = float(match_h) / program_node_height
    avg_scale = (scale_x + scale_y) * 0.5
    if avg_scale <= MIN_SCALE_RATIO:
        executor.log("✗ 锚点识别结果异常：节点尺寸过小，无法计算缩放比例", log_callback)
        return False

    # 比例始终固定为 1.0，仅使用锚点估计值做环境健康检查
    executor.scale_ratio = FIXED_SCALE_RATIO

    anchor_prog_x = float(anchor_program_pos[0])
    anchor_prog_y = float(anchor_program_pos[1])
    origin_x = (match_x - window_left) - anchor_prog_x * float(executor.scale_ratio)
    origin_y = (match_y - window_top) - anchor_prog_y * float(executor.scale_ratio)
    executor.origin_node_pos = (int(origin_x), int(origin_y))

    # 环境缩放健康检查：若锚点估计比例与固定比例差异过大，提示可能存在系统/编辑器缩放异常
    expected_scale = float(FIXED_SCALE_RATIO)
    scale_deviation = abs(float(avg_scale) - expected_scale)
    if scale_deviation >= 0.10:
        executor.log(
            f"· 环境检查：检测到锚点缩放≈{avg_scale:.4f}，与固定比例 {expected_scale:.4f} 差异较大，"
            f"请检查系统显示缩放与编辑器节点图缩放是否满足预期",
            log_callback,
        )

    executor.log(
        f"✓ 锚点坐标校准完成: 使用固定比例 {executor.scale_ratio:.4f}（锚点估计≈{avg_scale:.4f}）",
        log_callback,
    )
    executor.log(f"  原点窗口坐标: ({executor.origin_node_pos[0]}, {executor.origin_node_pos[1]})", log_callback)
    executor.log(f"  锚点程序坐标: ({anchor_prog_x:.1f}, {anchor_prog_y:.1f}) → 窗口定位 ({rel_x}, {rel_y})", log_callback)
    
    # 标记已通过锚点校准（区分于RANSAC估算）
    if hasattr(executor, "__dict__"):
        setattr(executor, "_scale_calibrated_by_anchor", True)
    
    return True


