from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import time

import cv2
import numpy as np
from PIL import Image

from .io_utils import _cv2_imwrite_unicode_safe, _get_debug_output_root_dir
from .models import SceneRecognizerTuning


def _apply_morphology_operations(
    binary_mask: np.ndarray,
    close_kernel: np.ndarray,
    open_kernel: np.ndarray,
    num_close_iterations: int,
    num_open_iterations: int,
) -> np.ndarray:
    processed_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, close_kernel, iterations=num_close_iterations)
    processed_mask = cv2.morphologyEx(processed_mask, cv2.MORPH_OPEN, open_kernel, iterations=num_open_iterations)
    return processed_mask


def _horizontal_overlap_ratio(rect_a: Dict, rect_b: Dict) -> float:
    ax1 = rect_a["x"]
    ax2 = rect_a["x"] + rect_a["width"]
    bx1 = rect_b["x"]
    bx2 = rect_b["x"] + rect_b["width"]
    overlap = max(0, min(ax2, bx2) - max(ax1, bx1))
    min_width = float(min(rect_a["width"], rect_b["width"]))
    if min_width <= 0:
        return 0.0
    return overlap / min_width


def _vertical_gap(rect_a: Dict, rect_b: Dict) -> int:
    ay1 = rect_a["y"]
    ay2 = rect_a["y"] + rect_a["height"]
    by1 = rect_b["y"]
    by2 = rect_b["y"] + rect_b["height"]
    if ay2 <= by1:
        return by1 - ay2
    if by2 <= ay1:
        return ay1 - by2
    return 0


def _bbox_iou_simple(rect_a: Tuple[int, int, int, int], rect_b: Tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = rect_a
    bx, by, bw, bh = rect_b
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return 0.0
    ax2 = ax + aw
    ay2 = ay + ah
    bx2 = bx + bw
    by2 = by + bh
    inter_x1 = max(ax, bx)
    inter_y1 = max(ay, by)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter_area = float((inter_x2 - inter_x1) * (inter_y2 - inter_y1))
    area_a = float(aw * ah)
    area_b = float(bw * bh)
    union_area = area_a + area_b - inter_area
    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


def _merge_vertically_near_overlapping_blocks(
    img_bgr: np.ndarray,
    img_hsv: np.ndarray,
    mask_final: np.ndarray,
    blocks: List[Dict],
    *,
    max_vertical_gap_px: int = 20,
    min_horizontal_overlap_ratio: float = 0.70,
) -> List[Dict]:
    if len(blocks) <= 1:
        return blocks

    rects = [{"x": b["x"], "y": b["y"], "width": b["width"], "height": b["height"]} for b in blocks]

    changed = True
    safe_guard = 0
    while changed and safe_guard < 1000:
        changed = False
        safe_guard += 1
        merged_indices = None
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                r1 = rects[i]
                r2 = rects[j]
                vgap = _vertical_gap(r1, r2)
                if vgap <= max_vertical_gap_px:
                    overlap_ratio = _horizontal_overlap_ratio(r1, r2)
                    if overlap_ratio >= min_horizontal_overlap_ratio:
                        nx1 = min(r1["x"], r2["x"])
                        ny1 = min(r1["y"], r2["y"])
                        nx2 = max(r1["x"] + r1["width"], r2["x"] + r2["width"])
                        ny2 = max(r1["y"] + r1["height"], r2["y"] + r2["height"])
                        rects.append({"x": nx1, "y": ny1, "width": nx2 - nx1, "height": ny2 - ny1})
                        merged_indices = (i, j)
                        changed = True
                        break
            if changed:
                break
        if changed and merged_indices is not None:
            i, j = merged_indices
            rects.pop(j)
            rects.pop(i)

    # 重新计算颜色/HSV信息（保持与旧实现一致，但后续不使用这些统计值）
    merged_blocks: List[Dict] = []
    for r in rects:
        x, y, w, h = r["x"], r["y"], r["width"], r["height"]
        area = w * h
        roi_hsv = img_hsv[y : y + h, x : x + w]
        roi_bgr = img_bgr[y : y + h, x : x + w]
        roi_mask = mask_final[y : y + h, x : x + w]
        masked_hsv = roi_hsv[roi_mask > 0]
        masked_bgr = roi_bgr[roi_mask > 0]
        if masked_hsv.size == 0 or masked_bgr.size == 0:
            avg_hue = 0.0
            avg_saturation = 0.0
            avg_value = 0.0
            avg_color_rgb = (0, 0, 0)
        else:
            avg_hue = float(np.mean(masked_hsv[:, 0]))
            avg_saturation = float(np.mean(masked_hsv[:, 1]))
            avg_value = float(np.mean(masked_hsv[:, 2]))
            avg_bgr = np.mean(masked_bgr, axis=0)
            avg_color_rgb = (int(avg_bgr[2]), int(avg_bgr[1]), int(avg_bgr[0]))
        merged_blocks.append(
            {
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "area": area,
                "color_rgb": avg_color_rgb,
                "hue": avg_hue,
                "saturation": avg_saturation,
                "value": avg_value,
            }
        )

    return merged_blocks


def _vertical_stripe_full_match_flags(
    image_array: np.ndarray,
    x_left: int,
    x_right: int,
    y_top: int,
    y_bottom: int,
    allowed_bg_colors_rgb: List[Tuple[int, int, int]],
    per_channel_tolerance: int,
    per_row_coverage_threshold: float,
) -> Tuple[bool, bool]:
    image_height, image_width = image_array.shape[:2]
    x_l = max(0, int(x_left))
    x_r = min(int(x_right), image_width)
    if x_r <= x_l:
        return False, False
    y_t = max(0, int(y_top))
    y_b = min(int(y_bottom), image_height - 1)
    if y_b < y_t:
        return False, False

    allowed_colors = [np.array([cr, cg, cb], dtype=np.int16) for (cr, cg, cb) in allowed_bg_colors_rgb]

    all_rows_bg = True
    all_rows_non_bg = True
    for y in range(y_t, y_b + 1):
        row_pixels = image_array[y, x_l:x_r, :]
        if row_pixels.size == 0:
            all_rows_bg = False
            continue
        matches = np.zeros(row_pixels.shape[0], dtype=bool)
        for color_vec in allowed_colors:
            diff = np.abs(row_pixels.astype(np.int16) - color_vec)
            cond = (
                (diff[:, 0] <= per_channel_tolerance)
                & (diff[:, 1] <= per_channel_tolerance)
                & (diff[:, 2] <= per_channel_tolerance)
            )
            matches = matches | cond
        coverage_ratio = float(np.count_nonzero(matches)) / float(matches.size) if matches.size > 0 else 0.0

        if coverage_ratio >= per_row_coverage_threshold:
            all_rows_non_bg = False
        else:
            all_rows_bg = False
        if (not all_rows_bg) and (not all_rows_non_bg):
            return False, False

    return all_rows_bg, all_rows_non_bg


def _refine_lateral_bounds_by_stripes(
    image_array: np.ndarray,
    region_x: int,
    region_width: int,
    content_top_y: int,
    content_bottom_y: int,
    allowed_bg_colors_rgb: List[Tuple[int, int, int]],
    per_channel_tolerance: int,
    stripe_width_px: int,
    per_row_coverage_threshold: float,
    enable_expand: bool = True,
    enable_shrink: bool = True,
) -> Tuple[int, int]:
    image_height, image_width = image_array.shape[:2]
    x = max(0, int(region_x))
    w = max(1, int(region_width))
    y_top = max(0, int(content_top_y))
    y_bottom = min(int(content_bottom_y), image_height - 1)
    if y_bottom < y_top:
        return x, w

    if enable_shrink:
        while w > stripe_width_px * 2:
            left_full_bg, left_full_non_bg = _vertical_stripe_full_match_flags(
                image_array,
                x,
                x + stripe_width_px,
                y_top,
                y_bottom,
                allowed_bg_colors_rgb,
                per_channel_tolerance,
                per_row_coverage_threshold,
            )
            right_full_bg, right_full_non_bg = _vertical_stripe_full_match_flags(
                image_array,
                x + w - stripe_width_px,
                x + w,
                y_top,
                y_bottom,
                allowed_bg_colors_rgb,
                per_channel_tolerance,
                per_row_coverage_threshold,
            )
            shrunk = False
            if left_full_non_bg:
                x += stripe_width_px
                w -= stripe_width_px
                shrunk = True
            if right_full_non_bg and w > stripe_width_px * 2:
                w -= stripe_width_px
                shrunk = True
            if not shrunk:
                break

    if enable_expand:
        while True:
            expanded = False
            if x - stripe_width_px >= 0:
                outside_left_full_bg, _ = _vertical_stripe_full_match_flags(
                    image_array,
                    x - stripe_width_px,
                    x,
                    y_top,
                    y_bottom,
                    allowed_bg_colors_rgb,
                    per_channel_tolerance,
                    per_row_coverage_threshold,
                )
                if outside_left_full_bg:
                    x -= stripe_width_px
                    w += stripe_width_px
                    expanded = True
            if x + w + stripe_width_px <= image_width:
                outside_right_full_bg, _ = _vertical_stripe_full_match_flags(
                    image_array,
                    x + w,
                    x + w + stripe_width_px,
                    y_top,
                    y_bottom,
                    allowed_bg_colors_rgb,
                    per_channel_tolerance,
                    per_row_coverage_threshold,
                )
                if outside_right_full_bg:
                    w += stripe_width_px
                    expanded = True
            if not expanded:
                break

    return x, w


def _find_content_bottom_with_probes(
    image_array: np.ndarray,
    region_x: int,
    region_bottom_y: int,
    region_width: int,
    allowed_bg_colors_rgb: List[Tuple[int, int, int]],
    per_channel_tolerance: int,
    probe_half_width: int,
    min_probe_coverage_ratio: float,
    stop_when_all_fail_consecutive: int,
    max_search_rows: Optional[int] = None,
) -> Optional[int]:
    image_height, image_width = image_array.shape[:2]
    if region_width <= 0:
        return None

    # 最小向下探索深度：从标题下方30px处才开始按探针规则判定
    initial_downward_offset_px = 30
    scan_start_y = max(0, int(region_bottom_y) + initial_downward_offset_px)
    scan_end_y = image_height - 1
    if max_search_rows is not None:
        scan_end_y = min(scan_end_y, scan_start_y + max(1, int(max_search_rows)))

    x_positions = [
        int(region_x + region_width * 1.0 / 10.0),
        int(region_x + region_width * 9.0 / 10.0),
        int(region_x + region_width * 1.0 / 2.0),
    ]
    x_positions = [min(max(0, x), image_width - 1) for x in x_positions]
    allowed_colors = [np.array([cr, cg, cb], dtype=np.int16) for (cr, cg, cb) in allowed_bg_colors_rgb]

    last_good_y: Optional[int] = None
    all_fail_streak = 0
    for scan_y in range(scan_start_y, scan_end_y + 1):
        probe_pass_flags: List[bool] = []
        for probe_center_x in x_positions:
            x_left = max(0, probe_center_x - probe_half_width)
            x_right = min(image_width, probe_center_x + probe_half_width + 1)
            if x_right <= x_left:
                probe_pass_flags.append(False)
                continue
            stripe_pixels = image_array[scan_y, x_left:x_right, :]
            if stripe_pixels.size == 0:
                probe_pass_flags.append(False)
                continue
            matches = np.zeros(stripe_pixels.shape[0], dtype=bool)
            for color_vec in allowed_colors:
                diff = np.abs(stripe_pixels.astype(np.int16) - color_vec)
                cond = (
                    (diff[:, 0] <= per_channel_tolerance)
                    & (diff[:, 1] <= per_channel_tolerance)
                    & (diff[:, 2] <= per_channel_tolerance)
                )
                matches = matches | cond
            coverage_ratio = float(np.count_nonzero(matches)) / float(matches.size) if matches.size > 0 else 0.0
            probe_pass_flags.append(coverage_ratio >= min_probe_coverage_ratio)

        if any(probe_pass_flags):
            last_good_y = scan_y
            all_fail_streak = 0
        else:
            all_fail_streak += 1
            if all_fail_streak >= max(1, int(stop_when_all_fail_consecutive)):
                break

    return last_good_y


def _detect_rectangles_from_canvas(
    canvas_image: Image.Image,
    *,
    tuning: Optional[SceneRecognizerTuning] = None,
) -> List[Dict]:
    effective_tuning = tuning or SceneRecognizerTuning()
    # 与旧实现相同的步骤：HSV双掩码 → 形态学 → 双向扫描去飞线 → 轮廓 → 合并
    print("\n" + "=" * 60)
    print("检测鲜亮色块（画布内）")
    print("=" * 60)

    debug_output_root_dir = _get_debug_output_root_dir()
    debug_steps_dir = Path(debug_output_root_dir) / "debug_steps"
    debug_steps_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    canvas_array = np.array(canvas_image)
    canvas_bgr = cv2.cvtColor(canvas_array, cv2.COLOR_RGB2BGR)
    canvas_hsv = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2HSV)
    img_height, img_width = canvas_hsv.shape[:2]

    # 掩码：彩色 + 白色/浅色
    saturation = canvas_hsv[:, :, 1]
    value = canvas_hsv[:, :, 2]
    mask_colorful = ((saturation > 50) & (value > 60)).astype(np.uint8) * 255
    mask_white = ((saturation < 50) & (value > 150)).astype(np.uint8) * 255

    step1_path = debug_steps_dir / f"{timestamp}_step1_color_mask_raw.png"
    _cv2_imwrite_unicode_safe(step1_path, mask_colorful)
    step2_path = debug_steps_dir / f"{timestamp}_step2_white_mask_raw.png"
    _cv2_imwrite_unicode_safe(step2_path, mask_white)

    # 形态学（分别处理后合并）
    kernel_close_color = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    kernel_close_white = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask_colorful = _apply_morphology_operations(mask_colorful, kernel_close_color, kernel_open, 2, 1)
    mask_white = _apply_morphology_operations(mask_white, kernel_close_white, kernel_open, 1, 1)
    step3_path = debug_steps_dir / f"{timestamp}_step3_color_mask_morphed.png"
    _cv2_imwrite_unicode_safe(step3_path, mask_colorful)
    step4_path = debug_steps_dir / f"{timestamp}_step4_white_mask_morphed.png"
    _cv2_imwrite_unicode_safe(step4_path, mask_white)

    mask_bright = cv2.bitwise_or(mask_colorful, mask_white)
    step5_path = debug_steps_dir / f"{timestamp}_step5_merged_mask.png"
    _cv2_imwrite_unicode_safe(step5_path, mask_bright)

    mask_filtered = mask_bright
    step6_path = debug_steps_dir / f"{timestamp}_step6_prescan_mask.png"
    _cv2_imwrite_unicode_safe(step6_path, mask_filtered)

    # 垂直扫描：删除高度小于阈值的小连通域
    scan_width = 5
    min_height_threshold = int(effective_tuning.color_scan_min_height_threshold_px)
    mask_no_lines = mask_filtered.copy()
    for x in range(0, img_width, scan_width):
        x_end = min(x + scan_width, img_width)
        strip = mask_no_lines[:, x:x_end].copy()
        contours_in_strip, _ = cv2.findContours(strip, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours_in_strip:
            _cx, _cy, _cw, ch = cv2.boundingRect(contour)
            if ch < min_height_threshold:
                cv2.drawContours(strip, [contour], -1, 0, thickness=-1)
        mask_no_lines[:, x:x_end] = strip
    step7_path = debug_steps_dir / f"{timestamp}_step7_vertical_scan.png"
    _cv2_imwrite_unicode_safe(step7_path, mask_no_lines)

    # 水平扫描：删除宽度小于阈值的小连通域
    scan_height = 1
    min_width_threshold = int(effective_tuning.color_scan_min_width_threshold_px)
    mask_no_lines_h = mask_no_lines.copy()
    for y in range(0, img_height, scan_height):
        y_end = min(y + scan_height, img_height)
        strip = mask_no_lines_h[y:y_end, :].copy()
        contours_in_strip, _ = cv2.findContours(strip, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours_in_strip:
            _cx, _cy, cw, _ch = cv2.boundingRect(contour)
            if cw < min_width_threshold:
                cv2.drawContours(strip, [contour], -1, 0, thickness=-1)
        mask_no_lines_h[y:y_end, :] = strip
    step8_path = debug_steps_dir / f"{timestamp}_step8_horizontal_scan.png"
    _cv2_imwrite_unicode_safe(step8_path, mask_no_lines_h)

    # 最终轮廓
    contours, _ = cv2.findContours(mask_no_lines_h, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    blocks: List[Dict] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        roi_hsv = canvas_hsv[y : y + h, x : x + w]
        roi_bgr = canvas_bgr[y : y + h, x : x + w]
        roi_mask = mask_no_lines_h[y : y + h, x : x + w]
        masked_hsv = roi_hsv[roi_mask > 0]
        masked_bgr = roi_bgr[roi_mask > 0]
        if masked_hsv.size == 0:
            continue
        avg_hue = float(np.mean(masked_hsv[:, 0])) if masked_hsv.size > 0 else 0.0
        avg_saturation = float(np.mean(masked_hsv[:, 1])) if masked_hsv.size > 0 else 0.0
        avg_value = float(np.mean(masked_hsv[:, 2])) if masked_hsv.size > 0 else 0.0
        avg_bgr = np.mean(masked_bgr, axis=0) if masked_bgr.size > 0 else (0.0, 0.0, 0.0)
        avg_color_rgb = (
            (int(avg_bgr[2]), int(avg_bgr[1]), int(avg_bgr[0])) if isinstance(avg_bgr, np.ndarray) else (0, 0, 0)
        )
        blocks.append(
            {
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
                "area": int(area),
                "color_rgb": avg_color_rgb,
                "hue": avg_hue,
                "saturation": avg_saturation,
                "value": avg_value,
            }
        )

    merged_blocks = _merge_vertically_near_overlapping_blocks(
        canvas_bgr,
        canvas_hsv,
        mask_no_lines_h,
        blocks,
        max_vertical_gap_px=int(effective_tuning.color_merge_max_vertical_gap_px),
        min_horizontal_overlap_ratio=0.70,
    )

    # 向下拓展到底部，并细化左右边界（保持与旧实现一致）
    content_bg_colors_rgb = [(62, 62, 67), (29, 29, 35)]
    content_color_tolerance = 8
    probe_half_width = 2
    min_probe_coverage_ratio = 0.60
    stop_when_all_fail_consecutive = 2
    lateral_stripe_width = max(2, probe_half_width)

    rectangles: List[Dict] = []
    for b in merged_blocks:
        bx = int(b["x"])
        by = int(b["y"])
        bw = int(b["width"])
        bh = int(b["height"])

        search_bottom_y = by + bh
        content_bottom_y = _find_content_bottom_with_probes(
            canvas_array,
            bx,
            search_bottom_y,
            bw,
            content_bg_colors_rgb,
            content_color_tolerance,
            probe_half_width,
            min_probe_coverage_ratio,
            stop_when_all_fail_consecutive,
            None,
        )
        final_x = bx
        final_w = bw
        final_h = bh
        if content_bottom_y is not None and content_bottom_y >= search_bottom_y:
            refined_x, refined_w = _refine_lateral_bounds_by_stripes(
                canvas_array,
                bx,
                bw,
                search_bottom_y,
                int(content_bottom_y),
                content_bg_colors_rgb,
                content_color_tolerance,
                lateral_stripe_width,
                min_probe_coverage_ratio,
                True,
                True,
            )
            final_x = int(refined_x)
            final_w = int(refined_w)
            final_h = int(content_bottom_y - by)
            if final_h < bh:
                final_h = bh

        rectangles.append(
            {
                "x": final_x,
                "y": by,
                "width": final_w,
                "height": final_h,
                # 记录“标题栏/顶部色块”高度：来源于色块检测阶段的原始块高度。
                # 该值是每个节点独立的动态测量结果，可用于替代全局 header_height 预估值。
                "header_height": int(bh),
            }
        )

    return rectangles


