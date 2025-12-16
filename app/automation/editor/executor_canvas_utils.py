# -*- coding: utf-8 -*-
"""
与节点图画布相关的通用工具：颜色吸附、几何兜底、安全点查找与可视化叠加层。

职责：
- 基于截图和一步式节点识别结果，在“节点图布置区域”内寻找允许背景色(#323237/#35353B)；
- 在存在节点 bbox 时，尽量将吸附点落在所有节点矩形之外，必要时按网格做几何兜底；
- 统一封装 `_emit_visual` 调用，输出画布区域、候选矩形与最终/兜底吸附点等调试叠加层。
"""

from __future__ import annotations

from typing import Optional, Callable, Tuple
from PIL import Image

from app.automation.editor.executor_protocol import EditorExecutorProtocol
from app.automation import capture as editor_capture
from app.automation.vision import list_nodes as vision_list_nodes


CANVAS_ALLOWED_COLORS: Tuple[str, str] = ("323237", "35353B")
CANVAS_COLOR_TOLERANCES: Tuple[int, int] = (10, 14)
CANVAS_COLOR_MAX_DISTANCES: Tuple[int, int] = (500, 2000)
CANVAS_FALLBACK_GRID_STEPS_X: int = 9
CANVAS_FALLBACK_GRID_STEPS_Y: int = 5
CANVAS_SAFE_POINT_NEAR_MAX_RADIUS: int = 160
CANVAS_SAFE_POINT_NEAR_STEP: int = 8
CANVAS_RECT_SAMPLE_STEPS_X: int = 4
CANVAS_RECT_SAMPLE_STEPS_Y: int = 4


def _is_point_inside_bbox(
    point_x: int,
    point_y: int,
    bbox_x: int,
    bbox_y: int,
    bbox_w: int,
    bbox_h: int,
) -> bool:
    """判断点是否落在给定矩形内部（带少量安全边距），用于避让已有节点区域。"""
    if int(bbox_w) <= 0 or int(bbox_h) <= 0:
        return False
    margin = 2
    left = int(bbox_x) - int(margin)
    top = int(bbox_y) - int(margin)
    right = int(bbox_x + bbox_w) + int(margin)
    bottom = int(bbox_y + bbox_h) + int(margin)
    if int(point_x) < left or int(point_x) >= right:
        return False
    if int(point_y) < top or int(point_y) >= bottom:
        return False
    return True


def _clamp_point_to_region(
    point_x: int,
    point_y: int,
    region_rect: Tuple[int, int, int, int],
) -> Tuple[int, int]:
    """将点裁剪到给定矩形内部，若矩形无效则返回原点。"""
    rx, ry, rw, rh = region_rect
    if int(rw) <= 0 or int(rh) <= 0:
        return int(point_x), int(point_y)
    clamped_x = int(point_x)
    clamped_y = int(point_y)
    if clamped_x < int(rx):
        clamped_x = int(rx)
    elif clamped_x >= int(rx + rw):
        clamped_x = int(rx + rw - 1)
    if clamped_y < int(ry):
        clamped_y = int(ry)
    elif clamped_y >= int(ry + rh):
        clamped_y = int(ry + rh - 1)
    return clamped_x, clamped_y


def _find_safe_point_in_region_by_grid(
    region_rect: Tuple[int, int, int, int],
    node_bboxes: list[Tuple[int, int, int, int]],
    steps_x: int,
    steps_y: int,
) -> Optional[Tuple[int, int]]:
    """在整个节点图区域内按网格粗采样寻找一个不落在任何节点矩形内的安全点。"""
    rx, ry, rw, rh = region_rect
    if int(rw) <= 0 or int(rh) <= 0:
        return None
    for iy in range(int(steps_y) + 1):
        for ix in range(int(steps_x) + 1):
            px = int(rx + (rw * ix) / max(int(steps_x), 1))
            py = int(ry + (rh * iy) / max(int(steps_y), 1))
            inside = False
            for bbox_x, bbox_y, bbox_w, bbox_h in node_bboxes:
                if _is_point_inside_bbox(int(px), int(py), int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h)):
                    inside = True
                    break
            if not inside:
                return int(px), int(py)
    return None


def _find_safe_point_near_editor(
    center_x: int,
    center_y: int,
    node_bboxes: list[Tuple[int, int, int, int]],
    region_rect: Tuple[int, int, int, int],
    max_radius: int = CANVAS_SAFE_POINT_NEAR_MAX_RADIUS,
    step: int = CANVAS_SAFE_POINT_NEAR_STEP,
) -> Optional[Tuple[int, int]]:
    """在给定中心点附近优先寻找一个不落在任何节点矩形内的安全点。"""
    rx, ry, rw, rh = region_rect
    if int(rw) <= 0 or int(rh) <= 0:
        return None
    for radius in range(int(step), int(max_radius) + int(step), int(step)):
        offsets = [
            (0, -radius),
            (radius, 0),
            (0, radius),
            (-radius, 0),
            (radius, -radius),
            (radius, radius),
            (-radius, radius),
            (-radius, -radius),
        ]
        for dx, dy in offsets:
            raw_px = int(center_x) + int(dx)
            raw_py = int(center_y) + int(dy)
            px, py = _clamp_point_to_region(int(raw_px), int(raw_py), (int(rx), int(ry), int(rw), int(rh)))
            inside = False
            for bbox_x, bbox_y, bbox_w, bbox_h in node_bboxes:
                if _is_point_inside_bbox(int(px), int(py), int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h)):
                    inside = True
                    break
            if not inside:
                return int(px), int(py)
    return None


def _find_safe_point_in_rect(
    rect_x: int,
    rect_y: int,
    rect_w: int,
    rect_h: int,
    node_bboxes: list[Tuple[int, int, int, int]],
) -> Optional[Tuple[int, int]]:
    """在给定矩形内部采样多个点，寻找不落在任何节点矩形内的安全点。"""
    if int(rect_w) <= 0 or int(rect_h) <= 0:
        return None
    steps_x = CANVAS_RECT_SAMPLE_STEPS_X
    steps_y = CANVAS_RECT_SAMPLE_STEPS_Y
    for iy in range(int(steps_y) + 1):
        for ix in range(int(steps_x) + 1):
            px = int(rect_x + (rect_w * ix) / max(int(steps_x), 1))
            py = int(rect_y + (rect_h * iy) / max(int(steps_y), 1))
            inside = False
            for bbox_x, bbox_y, bbox_w, bbox_h in node_bboxes:
                if _is_point_inside_bbox(int(px), int(py), int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h)):
                    inside = True
                    break
            if not inside:
                return int(px), int(py)
    return None


def _emit_visual_if_supported(
    executor: EditorExecutorProtocol,
    screenshot: Image.Image,
    overlay_rects: list[dict],
    overlay_circles: list[dict],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
) -> None:
    """统一封装可视化输出调用，避免多处重复 hasattr/callable 判断。"""
    emit_method = getattr(executor, "emit_visual", None)
    if callable(emit_method):
        emit_method(
            screenshot,
            {
                "rects": list(overlay_rects),
                "circles": list(overlay_circles),
            },
            visual_callback,
        )
        return
    private_emit = getattr(executor, "_emit_visual", None)
    if callable(private_emit):
        private_emit(
            screenshot,
            {
                "rects": list(overlay_rects),
                "circles": list(overlay_circles),
            },
            visual_callback,
        )


def snap_screen_point_to_canvas_background(
    executor: EditorExecutorProtocol,
    screen_x: int,
    screen_y: int,
    log_callback: Optional[Callable[[str], None]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> Optional[Tuple[int, int]]:
    """将屏幕坐标吸附到“节点图布置区域”的允许背景色上，并尽量避开已有节点矩形。"""
    win_rect = editor_capture.get_window_rect(executor.window_title)
    if win_rect is None:
        return None
    win_left, win_top, _win_right, _win_bottom = win_rect
    editor_x = int(screen_x) - int(win_left)
    editor_y = int(screen_y) - int(win_top)

    screenshot: Image.Image | None = None
    detected_nodes: list | None = None

    # 优先：在执行器开启场景级快照优化时，尝试复用当前视口下已缓存的 screenshot + list_nodes 结果，
    # 避免在连续创建/配置步骤中为颜色吸附重复触发整帧节点识别。
    get_scene_snapshot = getattr(executor, "get_scene_snapshot", None)
    if callable(get_scene_snapshot) and bool(
        getattr(executor, "enable_scene_snapshot_optimization", True)
    ):
        scene_snapshot = get_scene_snapshot()
        can_reuse = getattr(scene_snapshot, "can_reuse_for_current_view", None)
        if callable(can_reuse) and bool(can_reuse()):
            snapshot_image = getattr(scene_snapshot, "screenshot", None)
            snapshot_detections = getattr(scene_snapshot, "detected_nodes", None)
            if snapshot_image is not None and isinstance(snapshot_detections, list):
                screenshot = snapshot_image
                detected_nodes = snapshot_detections

        # 若当前视口下尚未建立场景帧，则由快照统一完成首帧截图与识别
        if screenshot is None or detected_nodes is None:
            ensure_frame = getattr(scene_snapshot, "ensure_frame", None)
            if callable(ensure_frame):
                frame, nodes = ensure_frame()
                screenshot = frame
                detected_nodes = nodes

    if screenshot is None:
        screenshot = editor_capture.capture_window_strict(executor.window_title)
        if screenshot is None:
            screenshot = editor_capture.capture_window(executor.window_title)
    if screenshot is None:
        return None

    rx, ry, rw, rh = editor_capture.get_region_rect(screenshot, "节点图布置区域")

    img_w, img_h = screenshot.size
    region_area = int(rw) * int(rh)
    if region_area <= 0 and int(img_w) > 0 and int(img_h) > 0:
        region_area = int(img_w) * int(img_h)
    super_large_threshold = int(region_area * 0.7) if region_area > 0 else 0
    executor.log(
        f"[颜色约束] 画布区域=({int(rx)},{int(ry)},{int(rw)},{int(rh)}) 区域面积={int(region_area)} 超大节点面积阈值={int(super_large_threshold)}",
        log_callback,
    )

    if detected_nodes is None:
        detected_nodes = vision_list_nodes(screenshot)
    node_bboxes_for_avoidance: list[Tuple[int, int, int, int]] = []
    skipped_super_large_count = 0
    for detected_node in detected_nodes:
        bbox = getattr(detected_node, "bbox", None)
        if not isinstance(bbox, tuple) or len(bbox) < 4:
            continue
        bbox_x, bbox_y, bbox_w, bbox_h = bbox
        if int(bbox_w) <= 0 or int(bbox_h) <= 0:
            continue
        bbox_x_i = int(bbox_x)
        bbox_y_i = int(bbox_y)
        bbox_w_i = int(bbox_w)
        bbox_h_i = int(bbox_h)
        if super_large_threshold > 0:
            area = int(bbox_w_i) * int(bbox_h_i)
            if area >= super_large_threshold:
                skipped_super_large_count += 1
                continue
        node_bboxes_for_avoidance.append((bbox_x_i, bbox_y_i, bbox_w_i, bbox_h_i))
    node_bboxes = node_bboxes_for_avoidance
    if node_bboxes:
        executor.log(
            f"[颜色约束] 节点识别：当前画布内检测到 {int(len(node_bboxes))} 个节点框(参与避让)，将尽量避开这些区域",
            log_callback,
        )
        max_preview = min(5, len(node_bboxes))
        for index in range(int(max_preview)):
            bbox_x_i, bbox_y_i, bbox_w_i, bbox_h_i = node_bboxes[index]
            executor.log(
                f"[颜色约束] 避让节点[{int(index)}] bbox=({int(bbox_x_i)},{int(bbox_y_i)},{int(bbox_w_i)},{int(bbox_h_i)})",
                log_callback,
            )
    if skipped_super_large_count > 0:
        executor.log(
            f"[颜色约束] 节点识别：额外忽略 {int(skipped_super_large_count)} 个面积近似整张画布的超大矩形，仅用于可视化，不参与避让",
            log_callback,
        )

    sample_color_hex = ""
    if int(editor_x) >= 0 and int(editor_x) < int(img_w) and int(editor_y) >= 0 and int(editor_y) < int(img_h):
        r, g, b = screenshot.getpixel((int(editor_x), int(editor_y)))
        sample_color_hex = f"{int(r):02X}{int(g):02X}{int(b):02X}"
        executor.log(
            f"[颜色约束] 取样: editor=({int(editor_x)},{int(editor_y)}) color=#{sample_color_hex} 画布区域=({int(rx)},{int(ry)},{int(rw)},{int(rh)})",
            log_callback,
        )

    if not (int(editor_x) >= int(rx) and int(editor_x) <= int(rx + rw) and int(editor_y) >= int(ry) and int(editor_y) <= int(ry + rh)):
        overlay_rects_outside: list[dict] = [
            {
                "bbox": (int(rx), int(ry), int(rw), int(rh)),
                "color": (120, 180, 255),
                "label": "节点图布置区域",
            }
        ]
        overlay_circles_outside: list[dict] = [
            {
                "center": (int(editor_x), int(editor_y)),
                "radius": 6,
                "color": (255, 60, 60),
                "label": "超出区域",
            }
        ]
        _emit_visual_if_supported(executor, screenshot, overlay_rects_outside, overlay_circles_outside, visual_callback)
        editor_x, editor_y = _clamp_point_to_region(int(editor_x), int(editor_y), (int(rx), int(ry), int(rw), int(rh)))
        if int(editor_x) >= 0 and int(editor_x) < int(img_w) and int(editor_y) >= 0 and int(editor_y) < int(img_h):
            r2, g2, b2 = screenshot.getpixel((int(editor_x), int(editor_y)))
            sample_color_hex = f"{int(r2):02X}{int(g2):02X}{int(b2):02X}"

    allowed_colors = CANVAS_ALLOWED_COLORS
    if sample_color_hex and (sample_color_hex in allowed_colors) and getattr(executor, "skip_color_snap_if_allowed", True):
        if node_bboxes:
            for bbox_x, bbox_y, bbox_w, bbox_h in node_bboxes:
                if _is_point_inside_bbox(int(editor_x), int(editor_y), int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h)):
                    executor.log(
                        "[颜色约束] 点击点虽为允许底色，但位于已有节点内部，强制进入吸附扫描以寻找空白区域",
                        log_callback,
                    )
                    break
            else:
                executor.log(f"[颜色约束] 点击点已为允许底色 #{sample_color_hex}，且未落在节点框内，跳过吸附", log_callback)
                executor.set_last_context_click_editor_pos(int(editor_x), int(editor_y))
                return (int(screen_x), int(screen_y))
        else:
            executor.log(f"[颜色约束] 点击点已为允许底色 #{sample_color_hex}，跳过吸附", log_callback)
            executor.set_last_context_click_editor_pos(int(editor_x), int(editor_y))
            return (int(screen_x), int(screen_y))

    overlay_rects: list[dict] = []
    overlay_circles: list[dict] = []
    overlay_rects.append(
        {
            "bbox": (int(rx), int(ry), int(rw), int(rh)),
            "color": (120, 180, 255),
            "label": "节点图布置区域",
        }
    )
    overlay_circles.append(
        {
            "center": (int(editor_x), int(editor_y)),
            "radius": 6,
            "color": (255, 200, 0),
            "label": "预选起点(原始)",
        }
    )
    for bbox_x, bbox_y, bbox_w, bbox_h in node_bboxes:
        overlay_rects.append(
            {
                "bbox": (int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h)),
                "color": (200, 140, 255),
                "label": "已存在节点",
            }
        )

    _emit_visual_if_supported(executor, screenshot, overlay_rects, overlay_circles, visual_callback)

    candidates: list[tuple[int, int, int, int, float, str]] = []
    color_scan_image = None

    for tolerance in CANVAS_COLOR_TOLERANCES:
        for max_distance in CANVAS_COLOR_MAX_DISTANCES:
            executor.log(
                f"[颜色约束] 搜索允许背景色: tol={int(tolerance)} max_d={int(max_distance)} near=({int(editor_x)},{int(editor_y)})",
                log_callback,
            )
            candidates.clear()
            if color_scan_image is None:
                color_scan_image = editor_capture.prepare_color_scan_image(screenshot)
            for color_hex in allowed_colors:
                rects = editor_capture.find_color_rectangles(
                    screenshot,
                    target_color_hex=str(color_hex),
                    color_tolerance=int(tolerance),
                    near_point=(int(editor_x), int(editor_y)),
                    max_distance=int(max_distance),
                    prepared_bgr=color_scan_image,
                )
                executor.log(f"  · 颜色#{str(color_hex)} 命中矩形数={int(len(rects))}", log_callback)
                for rect_x, rect_y, rect_w, rect_h, rect_distance in rects:
                    rect_center_x = int(rect_x + rect_w / 2)
                    rect_center_y = int(rect_y + rect_h / 2)
                    if not (rect_center_x >= int(rx) and rect_center_x < int(rx + rw) and rect_center_y >= int(ry) and rect_center_y < int(ry + rh)):
                        continue
                    candidates.append((int(rect_x), int(rect_y), int(rect_w), int(rect_h), float(rect_distance), str(color_hex)))
                    overlay_rects.append(
                        {
                            "bbox": (int(rect_x), int(rect_y), int(rect_w), int(rect_h)),
                            "color": (160, 220, 180),
                            "label": f"bg #{str(color_hex)} d={float(rect_distance):.0f}",
                        }
                    )
            if len(candidates) > 0:
                break
        if len(candidates) > 0:
            break

    if len(candidates) == 0:
        executor.log("✗ 未在画布内找到允许背景色(#323237/#35353B)，尝试按几何空隙兜底", log_callback)
        if sample_color_hex:
            sample_red = int(sample_color_hex[0:2], 16)
            sample_green = int(sample_color_hex[2:4], 16)
            sample_blue = int(sample_color_hex[4:6], 16)
            for allow in allowed_colors:
                allow_red = int(allow[0:2], 16)
                allow_green = int(allow[2:4], 16)
                allow_blue = int(allow[4:6], 16)
                diff_red = sample_red - allow_red
                diff_green = sample_green - allow_green
                diff_blue = sample_blue - allow_blue
                distance_value = (diff_red * diff_red + diff_green * diff_green + diff_blue * diff_blue) ** 0.5
                executor.log(
                    f"  · 样本色#{sample_color_hex} 相对允许#{allow}: Δ=({int(diff_red)},{int(diff_green)},{int(diff_blue)}) |dist|≈{float(distance_value):.1f}",
                    log_callback,
                )
        fallback_point = _find_safe_point_in_region_by_grid(
            (int(rx), int(ry), int(rw), int(rh)),
            node_bboxes,
            CANVAS_FALLBACK_GRID_STEPS_X,
            CANVAS_FALLBACK_GRID_STEPS_Y,
        )
        if fallback_point is None:
            if sample_color_hex:
                overlay_circles.append(
                    {
                        "center": (int(editor_x), int(editor_y)),
                        "radius": 8,
                        "color": (255, 120, 0),
                        "label": f"样本 #{sample_color_hex}",
                    }
                )
            _emit_visual_if_supported(executor, screenshot, overlay_rects, overlay_circles, visual_callback)
            return None

        safe_editor_x, safe_editor_y = fallback_point
        snapped_screen_x = int(win_left) + int(safe_editor_x)
        snapped_screen_y = int(win_top) + int(safe_editor_y)
        executor.set_last_context_click_editor_pos(int(safe_editor_x), int(safe_editor_y))
        executor.log(
            f"[颜色约束] 未命中允许背景色，按几何兜底选择空白点 editor=({int(safe_editor_x)},{int(safe_editor_y)})",
            log_callback,
        )
        overlay_circles.append(
            {
                "center": (int(safe_editor_x), int(safe_editor_y)),
                "radius": 7,
                "color": (255, 80, 80),
                "label": "几何兜底空白点",
            }
        )
        _emit_visual_if_supported(executor, screenshot, overlay_rects, overlay_circles, visual_callback)
        return (int(snapped_screen_x), int(snapped_screen_y))

    candidates.sort(key=lambda candidate: float(candidate[4]))
    chosen_rect: Optional[tuple[int, int, int, int, float, str]] = None
    chosen_editor_x: Optional[int] = None
    chosen_editor_y: Optional[int] = None

    for rect_x, rect_y, rect_w, rect_h, rect_distance, color_hex in candidates:
        candidate_editor_x = int(editor_x)
        if candidate_editor_x < int(rect_x):
            candidate_editor_x = int(rect_x)
        elif candidate_editor_x > int(rect_x + rect_w - 1):
            candidate_editor_x = int(rect_x + rect_w - 1)
        candidate_editor_y = int(editor_y)
        if candidate_editor_y < int(rect_y):
            candidate_editor_y = int(rect_y)
        elif candidate_editor_y > int(rect_y + rect_h - 1):
            candidate_editor_y = int(rect_y + rect_h - 1)

        inside_existing_node = False
        for bbox_x, bbox_y, bbox_w, bbox_h in node_bboxes:
            if _is_point_inside_bbox(candidate_editor_x, candidate_editor_y, int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h)):
                inside_existing_node = True
                executor.log(
                    f"[颜色约束] 候选吸附点 editor=({candidate_editor_x},{candidate_editor_y}) 落在节点矩形 ({int(bbox_x)},{int(bbox_y)},{int(bbox_w)},{int(bbox_h)}) 内，尝试在该矩形内寻找空白位置",
                    log_callback,
                )
                break
        if inside_existing_node:
            nearby_safe_point = _find_safe_point_near_editor(
                int(candidate_editor_x),
                int(candidate_editor_y),
                node_bboxes,
                (int(rx), int(ry), int(rw), int(rh)),
            )
            safe_point = nearby_safe_point
            if safe_point is None:
                safe_point = _find_safe_point_in_rect(int(rect_x), int(rect_y), int(rect_w), int(rect_h), node_bboxes)
            if safe_point is None:
                continue
            candidate_editor_x, candidate_editor_y = safe_point

        chosen_rect = (int(rect_x), int(rect_y), int(rect_w), int(rect_h), float(rect_distance), str(color_hex))
        chosen_editor_x = int(candidate_editor_x)
        chosen_editor_y = int(candidate_editor_y)
        executor.log(
            f"[颜色约束] 预选吸附点: rect=({int(rect_x)},{int(rect_y)},{int(rect_w)},{int(rect_h)}) "
            f"candidate_editor=({int(chosen_editor_x)},{int(chosen_editor_y)})",
            log_callback,
        )
        break

    if chosen_rect is None or chosen_editor_x is None or chosen_editor_y is None:
        executor.log("✗ 找到允许背景色候选，但全部落在已有节点内部，尝试按几何空隙兜底", log_callback)
        fallback_point = _find_safe_point_in_region_by_grid(
            (int(rx), int(ry), int(rw), int(rh)),
            node_bboxes,
            CANVAS_FALLBACK_GRID_STEPS_X,
            CANVAS_FALLBACK_GRID_STEPS_Y,
        )
        if fallback_point is None:
            overlay_circles.append(
                {
                    "center": (int(editor_x), int(editor_y)),
                    "radius": 8,
                    "color": (255, 80, 80),
                    "label": "候选均在节点内，且未找到几何空隙",
                }
            )
            _emit_visual_if_supported(executor, screenshot, overlay_rects, overlay_circles, visual_callback)
            return None

        safe_editor_x, safe_editor_y = fallback_point
        snapped_screen_x = int(win_left) + int(safe_editor_x)
        snapped_screen_y = int(win_top) + int(safe_editor_y)
        executor.set_last_context_click_editor_pos(int(safe_editor_x), int(safe_editor_y))
        executor.log(
            f"[颜色约束] 候选均在节点内，按几何兜底选择空白点 editor=({int(safe_editor_x)},{int(safe_editor_y)})",
            log_callback,
        )
        overlay_circles.append(
            {
                "center": (int(safe_editor_x), int(safe_editor_y)),
                "radius": 7,
                "color": (255, 80, 80),
                "label": "几何兜底空白点",
            }
        )
        _emit_visual_if_supported(executor, screenshot, overlay_rects, overlay_circles, visual_callback)
        return (int(snapped_screen_x), int(snapped_screen_y))

    rect_x = int(chosen_rect[0])
    rect_y = int(chosen_rect[1])
    rect_w = int(chosen_rect[2])
    rect_h = int(chosen_rect[3])
    color_hex = str(chosen_rect[5])

    if node_bboxes:
        still_inside = False
        for bbox_x, bbox_y, bbox_w, bbox_h in node_bboxes:
            if _is_point_inside_bbox(
                int(chosen_editor_x),
                int(chosen_editor_y),
                int(bbox_x),
                int(bbox_y),
                int(bbox_w),
                int(bbox_h),
            ):
                still_inside = True
                executor.log(
                    f"[颜色约束] 警告: 预选吸附结果 editor=({int(chosen_editor_x)},{int(chosen_editor_y)}) 仍位于节点矩形 ({int(bbox_x)},{int(bbox_y)},{int(bbox_w)},{int(bbox_h)}) 内，改用几何兜底点",
                    log_callback,
                )
                break
        if still_inside:
            fallback_point = _find_safe_point_in_region_by_grid(
                (int(rx), int(ry), int(rw), int(rh)),
                node_bboxes,
                CANVAS_FALLBACK_GRID_STEPS_X,
                CANVAS_FALLBACK_GRID_STEPS_Y,
            )
            if fallback_point is None:
                executor.log(
                    "[颜色约束] 几何兜底失败：在画布区域内未能找到任何不落在节点矩形内的安全点，本次吸附放弃",
                    log_callback,
                )
                overlay_circles.append(
                    {
                        "center": (int(chosen_editor_x), int(chosen_editor_y)),
                        "radius": 8,
                        "color": (255, 80, 80),
                        "label": "预选吸附点(仍在节点内)",
                    }
                )
                _emit_visual_if_supported(executor, screenshot, overlay_rects, overlay_circles, visual_callback)
                return None
            safe_editor_x, safe_editor_y = fallback_point
            snapped_screen_x = int(win_left) + int(safe_editor_x)
            snapped_screen_y = int(win_top) + int(safe_editor_y)
            executor.set_last_context_click_editor_pos(int(safe_editor_x), int(safe_editor_y))
            executor.log(
                f"[颜色约束] 预选吸附点在节点内，按几何兜底选择最终空白点 editor=({int(safe_editor_x)},{int(safe_editor_y)})",
                log_callback,
            )
            overlay_circles.append(
                {
                    "center": (int(safe_editor_x), int(safe_editor_y)),
                    "radius": 7,
                    "color": (255, 80, 80),
                    "label": f"最终吸附点(几何兜底) #{color_hex}",
                }
            )
            _emit_visual_if_supported(executor, screenshot, overlay_rects, overlay_circles, visual_callback)
            return (int(snapped_screen_x), int(snapped_screen_y))

    snapped_screen_x = int(win_left) + int(chosen_editor_x)
    snapped_screen_y = int(win_top) + int(chosen_editor_y)
    executor.set_last_context_click_editor_pos(int(chosen_editor_x), int(chosen_editor_y))

    executor.log(
        f"[颜色约束] 吸附结果: 目标(editor)=({int(editor_x)},{int(editor_y)}) → 吸附(editor)=({int(chosen_editor_x)},{int(chosen_editor_y)}) 颜色=#{color_hex} 候选数={int(len(candidates))}",
        log_callback,
    )
    overlay_rects.append(
        {
            "bbox": (int(rect_x), int(rect_y), int(rect_w), int(rect_h)),
            "color": (255, 120, 120),
            "label": "吸附矩形",
        }
    )
    overlay_circles.append(
        {
            "center": (int(chosen_editor_x), int(chosen_editor_y)),
            "radius": 7,
            "color": (255, 80, 80),
            "label": f"最终吸附点 #{color_hex}",
        }
    )
    _emit_visual_if_supported(executor, screenshot, overlay_rects, overlay_circles, visual_callback)

    return (int(snapped_screen_x), int(snapped_screen_y))



