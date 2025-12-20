# -*- coding: utf-8 -*-
"""
一步式场景识别模块：在一次图像处理流程中识别出节点矩形、节点标题与端口位置/序号。

输入：节点图画布区域的 PIL.Image（RGB）
输出：每个节点的矩形、标题（中文，仅当识别到文本时）、端口（侧别、序号、模板类型、坐标）。

注意：
- 不进行任何窗口截屏；仅对传入图像进行处理；
- 默认会把部分中间结果写入运行时缓存根目录下的 debug 子目录，便于排查识别问题（可通过环境变量 GRAPH_GENERATER_DEBUG_OUTPUT_ROOT 覆写输出根目录）；
- 不使用 try/except；错误直接抛出；
- 变量命名清晰可读，避免难以理解的缩写；
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Any
from pathlib import Path
import os
import time

import cv2
import numpy as np
from PIL import Image

# 注意：OCR 工具在函数内惰性导入，避免 tools 与 app.automation.vision 之间形成循环导入。


# ============================
# 可调参数（保留：OCR/模板匹配相关）
# ============================


@dataclass
class RecognizedPort:
    side: str  # 'left' | 'right'
    index: Optional[int]
    kind: str  # 模板名，如 'data', 'flow', 'settings', 'warning'
    bbox: Tuple[int, int, int, int]
    center: Tuple[int, int]
    confidence: float


@dataclass
class RecognizedNode:
    title_cn: str
    rect: Tuple[int, int, int, int]  # x, y, width, height（相对输入图像坐标）
    ports: List[RecognizedPort]


@dataclass
class TemplateMatchDebugInfo:
    """模板匹配调试信息（含被去重抑制的候选）。

    status:
        - "kept"：最终保留并参与端口构建的模板命中
        - "suppressed_nms"：在 NMS 阶段被抑制的候选（空间重叠）
        - "suppressed_same_row"：在同行去重阶段被抑制的候选（同一行仅保留一个）
    suppression_kind:
        - "nms"：NMS 抑制
        - "same_row"：同行去重
        - None：未被抑制
    """

    template_name: str
    bbox: Tuple[int, int, int, int]
    side: str
    index: Optional[int]
    confidence: float
    status: str
    suppression_kind: Optional[str]
    overlap_target_bbox: Optional[Tuple[int, int, int, int]]
    iou: Optional[float]


# ============================
# 基础工具
# ============================

 


_TEMPLATE_CACHE: Dict[str, Dict[str, np.ndarray]] = {}


def _cv2_imread_unicode_safe(image_path: Path, flags: int) -> Optional[np.ndarray]:
    """使用 OpenCV 的 imdecode 读取图片，兼容 Windows 中文路径。"""
    image_bytes = image_path.read_bytes()
    image_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    decoded_image = cv2.imdecode(image_buffer, flags)
    return decoded_image


def _cv2_imwrite_unicode_safe(image_path: Path, image_matrix: np.ndarray) -> None:
    """使用 OpenCV 的 imencode 写入图片，兼容 Windows 中文路径。"""
    file_extension = str(image_path.suffix or ".png").lower()
    success, encoded = cv2.imencode(file_extension, image_matrix)
    if not bool(success):
        raise ValueError(f"cv2.imencode 失败，无法写入：{image_path}")
    image_path.write_bytes(encoded.tobytes())


def _get_workspace_root_for_tools() -> Path:
    tools_dir = Path(__file__).resolve().parent
    return tools_dir.parent


def _get_debug_output_root_dir() -> Path:
    env_value = str(os.environ.get("GRAPH_GENERATER_DEBUG_OUTPUT_ROOT", "") or "").strip()
    if env_value:
        return Path(env_value)

    workspace_root = _get_workspace_root_for_tools()
    from engine.utils.cache.cache_paths import get_runtime_cache_root

    runtime_cache_root = get_runtime_cache_root(workspace_root)
    return runtime_cache_root / "debug" / "one_shot_scene_recognizer"


def _load_template_images(template_dir: str) -> Dict[str, np.ndarray]:
    templates: Dict[str, np.ndarray] = {}
    template_dir_path = Path(str(template_dir))
    if not template_dir_path.exists():
        return templates
    for template_file_path in sorted(
        template_dir_path.iterdir(), key=lambda candidate_path: candidate_path.name.lower()
    ):
        if not template_file_path.is_file():
            continue
        if template_file_path.suffix.lower() != ".png":
            continue
        template_image = _cv2_imread_unicode_safe(template_file_path, cv2.IMREAD_COLOR)
        if template_image is None:
            continue
        template_name = template_file_path.stem
        templates[template_name] = template_image
    return templates


def _get_or_load_templates(template_dir: str) -> Dict[str, np.ndarray]:
    """按目录缓存端口模板图像，避免在调试场景中重复从磁盘加载。"""
    cached = _TEMPLATE_CACHE.get(template_dir)
    if cached is not None:
        return cached
    templates = _load_template_images(template_dir)
    _TEMPLATE_CACHE[template_dir] = templates
    return templates


def _non_maximum_suppression(matches: List[Dict], overlap_threshold: float = 0.5) -> Tuple[List[Dict], List[Dict]]:
    """
    对模板匹配结果执行 NMS，返回：
    - filtered：保留下来的模板命中；
    - suppressed：被抑制的模板命中（附带抑制原因与 IoU / 目标框）。
    """
    if len(matches) == 0:
        return [], []
    matches_sorted = sorted(matches, key=lambda m: m['confidence'], reverse=True)
    filtered: List[Dict] = []
    suppressed: List[Dict] = []
    for current_match in matches_sorted:
        best_iou = 0.0
        overlap_target: Optional[Dict] = None
        for kept_match in filtered:
            x1_min = current_match['x']
            y1_min = current_match['y']
            x1_max = x1_min + current_match['width']
            y1_max = y1_min + current_match['height']

            x2_min = kept_match['x']
            y2_min = kept_match['y']
            x2_max = x2_min + kept_match['width']
            y2_max = y2_min + kept_match['height']

            inter_x_min = max(x1_min, x2_min)
            inter_y_min = max(y1_min, y2_min)
            inter_x_max = min(x1_max, x2_max)
            inter_y_max = min(y1_max, y2_max)

            if inter_x_max > inter_x_min and inter_y_max > inter_y_min:
                inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
                area1 = current_match['width'] * current_match['height']
                area2 = kept_match['width'] * kept_match['height']
                union_area = area1 + area2 - inter_area
                if union_area <= 0:
                    continue
                iou = inter_area / union_area
                if iou > overlap_threshold and iou > best_iou:
                    best_iou = iou
                    overlap_target = kept_match

        if overlap_target is not None:
            # 记录被 NMS 抑制的候选（reason='nms'，带 IoU 与目标框）
            suppressed_entry = dict(current_match)
            suppressed_entry['reason'] = 'nms'
            suppressed_entry['overlap_target_bbox'] = (
                int(overlap_target['x']),
                int(overlap_target['y']),
                int(overlap_target['width']),
                int(overlap_target['height']),
            )
            suppressed_entry['iou'] = float(best_iou)
            suppressed.append(suppressed_entry)
        else:
            filtered.append(current_match)
    return filtered, suppressed


# ============================
# 横线提取 + 合并 + 去重
# ============================

# （已移除旧横线配对法相关实现）


# （已移除旧横线配对法相关实现）


# （已移除旧横线配对法相关实现）


# （已移除旧横线配对法相关实现）


# （已移除旧横线配对法相关实现）


# ============================
# 色块方法所需辅助函数（与 color_block_detector 一致）
# ============================

def _apply_morphology_operations(binary_mask: np.ndarray,
                                 close_kernel: np.ndarray,
                                 open_kernel: np.ndarray,
                                 num_close_iterations: int,
                                 num_open_iterations: int) -> np.ndarray:
    processed_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, close_kernel, iterations=num_close_iterations)
    processed_mask = cv2.morphologyEx(processed_mask, cv2.MORPH_OPEN, open_kernel, iterations=num_open_iterations)
    return processed_mask


def _horizontal_overlap_ratio(rect_a: Dict, rect_b: Dict) -> float:
    ax1 = rect_a['x']
    ax2 = rect_a['x'] + rect_a['width']
    bx1 = rect_b['x']
    bx2 = rect_b['x'] + rect_b['width']
    overlap = max(0, min(ax2, bx2) - max(ax1, bx1))
    min_width = float(min(rect_a['width'], rect_b['width']))
    if min_width <= 0:
        return 0.0
    return overlap / min_width


def _vertical_gap(rect_a: Dict, rect_b: Dict) -> int:
    ay1 = rect_a['y']
    ay2 = rect_a['y'] + rect_a['height']
    by1 = rect_b['y']
    by2 = rect_b['y'] + rect_b['height']
    if ay2 <= by1:
        return by1 - ay2
    if by2 <= ay1:
        return ay1 - by2
    return 0


def _bbox_iou_simple(rect_a: Tuple[int, int, int, int],
                     rect_b: Tuple[int, int, int, int]) -> float:
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


def _merge_vertically_near_overlapping_blocks(img_bgr: np.ndarray,
                                              img_hsv: np.ndarray,
                                              mask_final: np.ndarray,
                                              blocks: List[Dict],
                                              max_vertical_gap_px: int = 20,
                                              min_horizontal_overlap_ratio: float = 0.70) -> List[Dict]:
    if len(blocks) <= 1:
        return blocks

    rects = [{'x': b['x'], 'y': b['y'], 'width': b['width'], 'height': b['height']} for b in blocks]

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
                        nx1 = min(r1['x'], r2['x'])
                        ny1 = min(r1['y'], r2['y'])
                        nx2 = max(r1['x'] + r1['width'], r2['x'] + r2['width'])
                        ny2 = max(r1['y'] + r1['height'], r2['y'] + r2['height'])
                        rects.append({'x': nx1, 'y': ny1, 'width': nx2 - nx1, 'height': ny2 - ny1})
                        merged_indices = (i, j)
                        changed = True
                        break
            if changed:
                break
        if changed and merged_indices is not None:
            i, j = merged_indices
            rects.pop(j)
            rects.pop(i)

    # 重新计算颜色/HSV信息（保持与 color_block_detector 一致，但后续不使用这些统计值）
    merged_blocks: List[Dict] = []
    for r in rects:
        x, y, w, h = r['x'], r['y'], r['width'], r['height']
        area = w * h
        roi_hsv = img_hsv[y:y+h, x:x+w]
        roi_bgr = img_bgr[y:y+h, x:x+w]
        roi_mask = mask_final[y:y+h, x:x+w]
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
        merged_blocks.append({
            'x': x,
            'y': y,
            'width': w,
            'height': h,
            'area': area,
            'color_rgb': avg_color_rgb,
            'hue': avg_hue,
            'saturation': avg_saturation,
            'value': avg_value
        })

    return merged_blocks


# ============================
# 色块方法：向下拓展与左右边界细化（与 color_block_detector 一致）
# ============================

def _vertical_stripe_full_match_flags(image_array: np.ndarray,
                                      x_left: int,
                                      x_right: int,
                                      y_top: int,
                                      y_bottom: int,
                                      allowed_bg_colors_rgb: List[Tuple[int, int, int]],
                                      per_channel_tolerance: int,
                                      per_row_coverage_threshold: float) -> Tuple[bool, bool]:
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
            cond = (diff[:, 0] <= per_channel_tolerance) & (diff[:, 1] <= per_channel_tolerance) & (diff[:, 2] <= per_channel_tolerance)
            matches = matches | cond
        coverage_ratio = float(np.count_nonzero(matches)) / float(matches.size) if matches.size > 0 else 0.0

        if coverage_ratio >= per_row_coverage_threshold:
            all_rows_non_bg = False
        else:
            all_rows_bg = False
        if not all_rows_bg and not all_rows_non_bg:
            return False, False

    return all_rows_bg, all_rows_non_bg


def _refine_lateral_bounds_by_stripes(image_array: np.ndarray,
                                      region_x: int,
                                      region_width: int,
                                      content_top_y: int,
                                      content_bottom_y: int,
                                      allowed_bg_colors_rgb: List[Tuple[int, int, int]],
                                      per_channel_tolerance: int,
                                      stripe_width_px: int,
                                      per_row_coverage_threshold: float,
                                      enable_expand: bool = True,
                                      enable_shrink: bool = True) -> Tuple[int, int]:
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
                image_array, x, x + stripe_width_px, y_top, y_bottom,
                allowed_bg_colors_rgb, per_channel_tolerance, per_row_coverage_threshold
            )
            right_full_bg, right_full_non_bg = _vertical_stripe_full_match_flags(
                image_array, x + w - stripe_width_px, x + w, y_top, y_bottom,
                allowed_bg_colors_rgb, per_channel_tolerance, per_row_coverage_threshold
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
                    image_array, x - stripe_width_px, x, y_top, y_bottom,
                    allowed_bg_colors_rgb, per_channel_tolerance, per_row_coverage_threshold
                )
                if outside_left_full_bg:
                    x -= stripe_width_px
                    w += stripe_width_px
                    expanded = True
            if x + w + stripe_width_px <= image_width:
                outside_right_full_bg, _ = _vertical_stripe_full_match_flags(
                    image_array, x + w, x + w + stripe_width_px, y_top, y_bottom,
                    allowed_bg_colors_rgb, per_channel_tolerance, per_row_coverage_threshold
                )
                if outside_right_full_bg:
                    w += stripe_width_px
                    expanded = True
            if not expanded:
                break

    return x, w


def _find_content_bottom_with_probes(image_array: np.ndarray,
                                     region_x: int,
                                     region_bottom_y: int,
                                     region_width: int,
                                     allowed_bg_colors_rgb: List[Tuple[int, int, int]],
                                     per_channel_tolerance: int,
                                     probe_half_width: int,
                                     min_probe_coverage_ratio: float,
                                     stop_when_all_fail_consecutive: int,
                                     max_search_rows: Optional[int] = None) -> Optional[int]:
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
        int(region_x + region_width * 1.0 / 2.0)
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
                cond = (diff[:, 0] <= per_channel_tolerance) & (diff[:, 1] <= per_channel_tolerance) & (diff[:, 2] <= per_channel_tolerance)
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


# ============================
# OCR（拼图式）
# ============================

def _ocr_titles_for_rectangles(screenshot: Image.Image, rectangles: List[Dict], header_height: int = 28) -> Dict[int, str]:
    if len(rectangles) == 0:
        return {}
    from app.automation.vision.ocr_utils import get_ocr_engine, extract_chinese

    ocr_engine = get_ocr_engine()

    min_tile_height = 48
    max_tile_width = 800
    tile_gap = 8
    tile_padding = 2
    max_row_width = 2400

    block_tiles: List[Dict] = []
    for idx, rect in enumerate(rectangles, 1):
        rect_x = rect['x']
        rect_y = rect['y']
        rect_width = rect['width']
        header_top = rect_y
        header_bottom = min(rect_y + header_height, screenshot.size[1])
        header_left = rect_x
        header_right = min(rect_x + rect_width, screenshot.size[0])
        left = max(0, header_left + tile_padding)
        top = max(0, header_top + tile_padding)
        right = min(screenshot.size[0], header_right - tile_padding)
        bottom = min(screenshot.size[1], header_bottom - tile_padding)
        if right <= left or bottom <= top:
            continue
        roi = screenshot.crop((left, top, right, bottom))
        scale_height = min_tile_height / float(max(1, roi.size[1])) if roi.size[1] < min_tile_height else 1.0
        scale_width_cap = max_row_width / float(max(1, roi.size[0]))
        scale_factor = min(scale_width_cap, max(1.0, scale_height))
        if abs(scale_factor - 1.0) > 1e-3:
            new_w = max(1, int(roi.size[0] * scale_factor))
            new_h = max(1, int(roi.size[1] * scale_factor))
            roi = roi.resize((new_w, new_h), Image.BILINEAR)
        block_tiles.append({'idx': idx, 'image': roi})

    placements: List[Tuple[int, int]] = []
    current_x = tile_gap
    current_y = tile_gap
    row_height = 0
    for tile in block_tiles:
        tw, th = tile['image'].size
        if current_x + tw + tile_gap > max_row_width:
            current_x = tile_gap
            current_y += row_height + tile_gap
            row_height = 0
        placements.append((current_x, current_y))
        current_x += tw + tile_gap
        if th > row_height:
            row_height = th
    canvas_width = max_row_width
    canvas_height = current_y + row_height + tile_gap if len(block_tiles) > 0 else (tile_gap * 2)

    montage = Image.new('RGB', (canvas_width, canvas_height), (0, 0, 0))
    for tile, (px, py) in zip(block_tiles, placements):
        montage.paste(tile['image'], (px, py))

    tile_rects: List[Dict] = []
    for tile, (px, py) in zip(block_tiles, placements):
        tw, th = tile['image'].size
        tile_rects.append({'idx': tile['idx'], 'x': px, 'y': py, 'w': tw, 'h': th})

    montage_array = np.array(montage)
    ocr_result_full, _ = ocr_engine(montage_array)

    texts_by_rect: Dict[int, List[Tuple[int, int, str]]] = {i: [] for i in range(1, len(rectangles) + 1)}
    if ocr_result_full:
        for item in ocr_result_full:
            box = item[0]
            text = item[1]
            xs = [int(pt[0]) for pt in box]
            ys = [int(pt[1]) for pt in box]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            for rect in tile_rects:
                if rect['x'] <= cx <= rect['x'] + rect['w'] and rect['y'] <= cy <= rect['y'] + rect['h']:
                    texts_by_rect[rect['idx']].append((y1, x1, text))
                    break

    ocr_results: Dict[int, str] = {}
    for idx in range(1, len(rectangles) + 1):
        items = texts_by_rect[idx]
        if len(items) == 0:
            continue
        items.sort(key=lambda t: (t[0], t[1]))
        merged_text = " ".join([t[2] for t in items]).strip()
        chinese_only = extract_chinese(merged_text)
        if chinese_only:
            ocr_results[idx] = chinese_only
    return ocr_results


# ============================
# 模板匹配（端口）
# ============================

def _get_effective_template_threshold(
    template_name: str,
    base_threshold: float,
) -> float:
    """
    根据模板名称返回实际使用的匹配阈值。

    规则：
    - 绝大多数端口模板使用统一的 base_threshold；
    - 名称以 "process" 开头的流程端口模板（如 "Process", "Process2"）使用最小阈值 0.70；
    - 名称以 "generic" 开头的泛型端口模板（如 "Generic", "Generic2"）使用最小阈值 0.75；
    - 实际使用的阈值为 min(base_threshold, 模板最小阈值)，避免在调试场景中比调用方要求更严格。
    """
    normalized_name = template_name.strip().lower()
    minimum_threshold: Optional[float] = None
    if normalized_name.startswith("process"):
        minimum_threshold = 0.70
    elif normalized_name.startswith("generic"):
        minimum_threshold = 0.75
    if minimum_threshold is None:
        return base_threshold
    return float(min(base_threshold, minimum_threshold))


def _match_templates_in_rectangle(
    screenshot: Image.Image,
    rect: Dict,
    templates: Dict[str, np.ndarray],
    header_height: int = 28,
    threshold: float = 0.7,
    debug_entries: Optional[List[TemplateMatchDebugInfo]] = None,
) -> List[Dict]:
    rect_x = rect['x']
    rect_y = rect['y']
    rect_width = rect['width']
    rect_height = rect['height']
    search_top = rect_y + header_height
    search_bottom = rect_y + rect_height
    search_left = rect_x
    search_right = rect_x + rect_width
    if search_top >= search_bottom or search_left >= search_right:
        return []
    if search_top >= screenshot.size[1] or search_left >= screenshot.size[0]:
        return []
    search_bottom = min(search_bottom, screenshot.size[1])
    search_right = min(search_right, screenshot.size[0])
    search_region = screenshot.crop((search_left, search_top, search_right, search_bottom))
    search_array = cv2.cvtColor(np.array(search_region), cv2.COLOR_RGB2BGR)
    matches: List[Dict] = []
    for template_name, template_image in templates.items():
        template_height, template_width = template_image.shape[:2]
        per_template_threshold = _get_effective_template_threshold(template_name, float(threshold))
        if search_array.shape[0] < template_height or search_array.shape[1] < template_width:
            continue
        result = cv2.matchTemplate(search_array, template_image, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= per_template_threshold)
        for location in zip(*locations[::-1]):
            match_x = search_left + location[0]
            match_y = search_top + location[1]
            confidence_value = float(result[location[1], location[0]])
            matches.append(
                {
                    "template_name": template_name,
                    "x": int(match_x),
                    "y": int(match_y),
                    "width": int(template_width),
                    "height": int(template_height),
                    "confidence": confidence_value,
                }
            )

    matches_after_nms, suppressed_by_nms = _non_maximum_suppression(matches, overlap_threshold=0.1)
    rect_center_x = rect_x + rect_width / 2.0
    for match in matches_after_nms:
        match_center_x = match["x"] + match["width"] / 2.0
        match["side"] = "left" if match_center_x < rect_center_x else "right"
    for suppressed_match in suppressed_by_nms:
        match_center_x = suppressed_match["x"] + suppressed_match["width"] / 2.0
        suppressed_match["side"] = "left" if match_center_x < rect_center_x else "right"
    # 非索引类模板（装饰项）：不参与同行去重
    # - Settings* / Warning*：本来就不需要索引
    # - Dictionary*：与 Settings 归为同一类装饰控件，不做同行去重
    def is_no_index_template_name(template_name: str) -> bool:
        normalized_name = str(template_name).lower()
        return (
            normalized_name.startswith("settings")
            or normalized_name.startswith("warning")
            or normalized_name.startswith("dictionary")
        )
    # 同行容差（像素）
    y_tolerance = 10

    left_matches_initial = sorted(
        [match for match in matches_after_nms if match["side"] == "left"],
        key=lambda match: match["y"],
    )
    right_matches_initial = sorted(
        [match for match in matches_after_nms if match["side"] == "right"],
        key=lambda match: match["y"],
    )

    def filter_same_row_ports(side_matches: List[Dict], keep_leftmost: bool) -> List[Dict]:
        if len(side_matches) == 0:
            return []
        filtered_matches: List[Dict] = []
        current_index_value = 0
        current_index = 0
        while current_index < len(side_matches):
            current_match = side_matches[current_index]
            same_row_matches = [current_match]
            next_index = current_index + 1
            while next_index < len(side_matches):
                if abs(side_matches[next_index]["y"] - current_match["y"]) <= y_tolerance:
                    same_row_matches.append(side_matches[next_index])
                    next_index += 1
                else:
                    break
            indexed_items = [
                match
                for match in same_row_matches
                if not is_no_index_template_name(match["template_name"])
            ]
            no_index_items = [
                match
                for match in same_row_matches
                if is_no_index_template_name(match["template_name"])
            ]
            if len(indexed_items) > 1:
                keeper = (
                    min(indexed_items, key=lambda match: match["x"])
                    if keep_leftmost
                    else max(indexed_items, key=lambda match: match["x"])
                )
                keeper["index"] = current_index_value
                current_index_value += 1
                filtered_matches.append(keeper)
            elif len(indexed_items) == 1:
                single_kept = indexed_items[0]
                single_kept["index"] = current_index_value
                current_index_value += 1
                filtered_matches.append(single_kept)
            for item in no_index_items:
                item["index"] = None
                filtered_matches.append(item)
            current_index = next_index
        return filtered_matches

    left_matches = filter_same_row_ports(list(left_matches_initial), keep_leftmost=True)
    right_matches = filter_same_row_ports(list(right_matches_initial), keep_leftmost=False)
    left_matches.sort(key=lambda match: match["y"])
    right_matches.sort(key=lambda match: match["y"])
    final_matches = left_matches + right_matches

    if debug_entries is not None:
        final_match_set = set(id(match) for match in final_matches)
        suppressed_same_row: List[Dict] = []
        for original_match in left_matches_initial + right_matches_initial:
            if id(original_match) not in final_match_set:
                suppressed_same_row.append(original_match)

        for match in final_matches:
            debug_entries.append(
                TemplateMatchDebugInfo(
                    template_name=str(match["template_name"]),
                    bbox=(int(match["x"]), int(match["y"]), int(match["width"]), int(match["height"])),
                    side=str(match.get("side", "")),
                    index=match.get("index"),
                    confidence=float(match.get("confidence", 0.0)),
                    status="kept",
                    suppression_kind=None,
                    overlap_target_bbox=None,
                    iou=None,
                )
            )

        for suppressed_match in suppressed_same_row:
            debug_entries.append(
                TemplateMatchDebugInfo(
                    template_name=str(suppressed_match["template_name"]),
                    bbox=(
                        int(suppressed_match["x"]),
                        int(suppressed_match["y"]),
                        int(suppressed_match["width"]),
                        int(suppressed_match["height"]),
                    ),
                    side=str(suppressed_match.get("side", "")),
                    index=suppressed_match.get("index"),
                    confidence=float(suppressed_match.get("confidence", 0.0)),
                    status="suppressed_same_row",
                    suppression_kind="same_row",
                    overlap_target_bbox=None,
                    iou=None,
                )
            )

        for suppressed_match in suppressed_by_nms:
            overlap_bbox = suppressed_match.get("overlap_target_bbox")
            debug_entries.append(
                TemplateMatchDebugInfo(
                    template_name=str(suppressed_match["template_name"]),
                    bbox=(
                        int(suppressed_match["x"]),
                        int(suppressed_match["y"]),
                        int(suppressed_match["width"]),
                        int(suppressed_match["height"]),
                    ),
                    side=str(suppressed_match.get("side", "")),
                    index=suppressed_match.get("index"),
                    confidence=float(suppressed_match.get("confidence", 0.0)),
                    status="suppressed_nms",
                    suppression_kind="nms",
                    overlap_target_bbox=None
                    if overlap_bbox is None
                    else (
                        int(overlap_bbox[0]),
                        int(overlap_bbox[1]),
                        int(overlap_bbox[2]),
                        int(overlap_bbox[3]),
                    ),
                    iou=float(suppressed_match.get("iou", 0.0)),
                )
            )

    return final_matches


def debug_match_templates_for_rectangle(
    canvas_image: Image.Image,
    rect: Dict,
    template_dir: str,
    header_height: int = 28,
    threshold: float = 0.7,
) -> List[TemplateMatchDebugInfo]:
    """
    在单个节点矩形内执行模板匹配，返回包含去重抑制信息的调试结果。

    仅用于调试/可视化场景，不参与正式识别管线。
    """
    templates = _get_or_load_templates(template_dir)
    debug_entries: List[TemplateMatchDebugInfo] = []
    _match_templates_in_rectangle(
        canvas_image,
        rect,
        templates,
        header_height,
        threshold,
        debug_entries,
    )
    return debug_entries


# ============================
# 主流程
# ============================

def _detect_rectangles_from_canvas(canvas_image: Image.Image) -> List[Dict]:
    # 与 color_block_detector.py 相同的步骤：HSV双掩码 → 形态学 → 双向扫描去飞线 → 轮廓 → 合并
    print("\n" + "=" * 60)
    print("检测鲜亮色块（画布内）")
    print("=" * 60)

    # 调试输出目录：默认落在运行时缓存根目录下的 debug/ 子目录，可通过环境变量覆写
    debug_output_root_dir = _get_debug_output_root_dir()
    debug_steps_dir = debug_output_root_dir / "debug_steps"
    debug_steps_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # 转换
    canvas_array = np.array(canvas_image)
    canvas_bgr = cv2.cvtColor(canvas_array, cv2.COLOR_RGB2BGR)
    canvas_hsv = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2HSV)
    img_height, img_width = canvas_hsv.shape[:2]

    # 掩码：彩色 + 白色/浅色
    saturation = canvas_hsv[:, :, 1]
    value = canvas_hsv[:, :, 2]
    mask_colorful = ((saturation > 50) & (value > 60)).astype(np.uint8) * 255
    mask_white = ((saturation < 50) & (value > 150)).astype(np.uint8) * 255

    # 保存原始掩码
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

    # 直接进入双向扫描去飞线
    mask_filtered = mask_bright
    step6_path = debug_steps_dir / f"{timestamp}_step6_prescan_mask.png"
    _cv2_imwrite_unicode_safe(step6_path, mask_filtered)

    # 垂直扫描：删除高度小于阈值的小连通域
    scan_width = 5
    min_height_threshold = 15
    mask_no_lines = mask_filtered.copy()
    removed_pixels = 0
    for x in range(0, img_width, scan_width):
        x_end = min(x + scan_width, img_width)
        strip = mask_no_lines[:, x:x_end].copy()
        contours_in_strip, _ = cv2.findContours(strip, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours_in_strip:
            cx, cy, cw, ch = cv2.boundingRect(contour)
            if ch < min_height_threshold:
                cv2.drawContours(strip, [contour], -1, 0, thickness=-1)
                removed_pixels += int(cv2.contourArea(contour))
        mask_no_lines[:, x:x_end] = strip
    step7_path = debug_steps_dir / f"{timestamp}_step7_vertical_scan.png"
    _cv2_imwrite_unicode_safe(step7_path, mask_no_lines)

    # 水平扫描：删除宽度小于阈值的小连通域
    scan_height = 1
    min_width_threshold = 50
    mask_no_lines_h = mask_no_lines.copy()
    removed_pixels_h = 0
    for y in range(0, img_height, scan_height):
        y_end = min(y + scan_height, img_height)
        strip = mask_no_lines_h[y:y_end, :].copy()
        contours_in_strip, _ = cv2.findContours(strip, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours_in_strip:
            cx, cy, cw, ch = cv2.boundingRect(contour)
            if cw < min_width_threshold:
                cv2.drawContours(strip, [contour], -1, 0, thickness=-1)
                removed_pixels_h += int(cv2.contourArea(contour))
        mask_no_lines_h[y:y_end, :] = strip
    step8_path = debug_steps_dir / f"{timestamp}_step8_horizontal_scan.png"
    _cv2_imwrite_unicode_safe(step8_path, mask_no_lines_h)

    # 最终轮廓
    contours, _ = cv2.findContours(mask_no_lines_h, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    blocks: List[Dict] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        roi_hsv = canvas_hsv[y:y+h, x:x+w]
        roi_bgr = canvas_bgr[y:y+h, x:x+w]
        roi_mask = mask_no_lines_h[y:y+h, x:x+w]
        masked_hsv = roi_hsv[roi_mask > 0]
        masked_bgr = roi_bgr[roi_mask > 0]
        if masked_hsv.size == 0:
            continue
        avg_hue = float(np.mean(masked_hsv[:, 0])) if masked_hsv.size > 0 else 0.0
        avg_saturation = float(np.mean(masked_hsv[:, 1])) if masked_hsv.size > 0 else 0.0
        avg_value = float(np.mean(masked_hsv[:, 2])) if masked_hsv.size > 0 else 0.0
        avg_bgr = np.mean(masked_bgr, axis=0) if masked_bgr.size > 0 else (0.0, 0.0, 0.0)
        avg_color_rgb = (int(avg_bgr[2]), int(avg_bgr[1]), int(avg_bgr[0])) if isinstance(avg_bgr, np.ndarray) else (0, 0, 0)
        blocks.append({
            'x': int(x),
            'y': int(y),
            'width': int(w),
            'height': int(h),
            'area': int(area),
            'color_rgb': avg_color_rgb,
            'hue': avg_hue,
            'saturation': avg_saturation,
            'value': avg_value
        })

    # 合并相邻色块（与 color_block_detector 相同规则）
    merged_blocks = _merge_vertically_near_overlapping_blocks(
        canvas_bgr,
        canvas_hsv,
        mask_no_lines_h,
        blocks,
        max_vertical_gap_px=20,
        min_horizontal_overlap_ratio=0.70,
    )

    # 向下拓展到底部，并细化左右边界（与 color_block_detector 相同思路）
    content_bg_colors_rgb = [(62, 62, 67), (29, 29, 35)]
    content_color_tolerance = 8
    probe_half_width = 2
    min_probe_coverage_ratio = 0.60
    stop_when_all_fail_consecutive = 2
    lateral_stripe_width = max(2, probe_half_width)

    # 转为 rectangles 输出结构
    rectangles: List[Dict] = []
    for b in merged_blocks:
        bx = int(b['x'])
        by = int(b['y'])
        bw = int(b['width'])
        bh = int(b['height'])
        # 计算内容区底部（从标题矩形下边缘继续向下）
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
            None
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
                True
            )
            final_x = int(refined_x)
            final_w = int(refined_w)
            final_h = int(content_bottom_y - by)
            if final_h < bh:
                final_h = bh

        rectangles.append({
            'x': final_x,
            'y': by,
            'width': final_w,
            'height': final_h,
        })
    return rectangles


def recognize_scene(canvas_image: Image.Image,
                    template_dir: str,
                    header_height: int = 28,
                    threshold: float = 0.7) -> List[RecognizedNode]:
    """
    在一次调用中识别节点矩形、标题与端口。

    Args:
        canvas_image: 仅为“节点图布置区域”的图像（PIL.Image，RGB）。
        template_dir: 端口模板目录（PNG），例如 'assets/ocr_templates/4K-CN/Node'。
        header_height: 节点卡片顶部标题高度（像素）。
        threshold: 模板匹配阈值。

    Returns:
        List[RecognizedNode]:
            每个节点包含标题、矩形与端口。
    """
    rectangles = _detect_rectangles_from_canvas(canvas_image)
    if len(rectangles) == 0:
        return []

    from app.automation.vision.ocr_utils import extract_chinese

    titles_by_index = _ocr_titles_for_rectangles(canvas_image, rectangles, header_height=header_height)
    templates = _load_template_images(template_dir)

    recognized_nodes: List[RecognizedNode] = []
    for idx, rect in enumerate(rectangles, 1):
        node_title = titles_by_index.get(idx, "")
        node_title_cn = extract_chinese(node_title)
        template_matches = _match_templates_in_rectangle(
            canvas_image,
            rect,
            templates,
            header_height,
            threshold,
        )
        recognized_ports: List[RecognizedPort] = []
        for match in template_matches:
            center_x = int(match['x'] + match['width'] / 2)
            center_y = int(match['y'] + match['height'] / 2)
            recognized_ports.append(
                RecognizedPort(
                    side=match['side'],
                    index=match.get('index'),
                    kind=str(match['template_name']),
                    bbox=(int(match['x']), int(match['y']), int(match['width']), int(match['height'])),
                    center=(center_x, center_y),
                    confidence=float(match['confidence']),
                )
            )

        # Settings / Warning 行内重判规则使用统一的“装饰端口”判定
        y_tolerance = 10

        def is_decorative_port(port_obj: RecognizedPort) -> bool:
            """判定是否为行内装饰/控件类模板（不可连线）。

            说明：
            - 一步式识别的 kind 来源为模板文件名，存在 Settings2 / Warning2 之类变体；
              因此统一使用 startswith 做归类，避免漏判导致侧别重判与去重策略失效。
            - Dictionary/Select 与 Settings 同属行内控件，不应参与“可连线端口行”的推断。
            """
            kind_lower = str(port_obj.kind or "").lower()
            return (
                kind_lower.startswith("settings")
                or kind_lower.startswith("warning")
                or kind_lower.startswith("dictionary")
                or kind_lower.startswith("select")
            )

        def is_connectable_like_port(port_obj: RecognizedPort) -> bool:
            return not is_decorative_port(port_obj)

        def is_settings_like_port(port_obj: RecognizedPort) -> bool:
            return str(port_obj.kind or "").lower().startswith("settings")

        def is_warning_like_port(port_obj: RecognizedPort) -> bool:
            return str(port_obj.kind or "").lower().startswith("warning")

        def _has_connectable_neighbor_on_side(
            *,
            ports: List[RecognizedPort],
            row_center_y: int,
            side: str,
        ) -> bool:
            return any(
                (neighbor.side == side)
                and is_connectable_like_port(neighbor)
                and (abs(int(neighbor.center[1]) - int(row_center_y)) <= y_tolerance)
                for neighbor in ports
            )

        # Settings 侧别归因（绑定到可连线端口行）：
        # - 若同行（±y_tolerance）仅左侧存在可连线端口：Settings 归为 left
        # - 若同行（±y_tolerance）仅右侧存在可连线端口：Settings 归为 right
        # - 若两侧均存在或两侧均不存在：保持原侧别（x 相对节点中心线的初判）
        for settings_port in recognized_ports:
            if not is_settings_like_port(settings_port):
                continue
            row_center_y = int(settings_port.center[1])
            has_left_connectable = _has_connectable_neighbor_on_side(
                ports=recognized_ports,
                row_center_y=row_center_y,
                side="left",
            )
            has_right_connectable = _has_connectable_neighbor_on_side(
                ports=recognized_ports,
                row_center_y=row_center_y,
                side="right",
            )
            if has_left_connectable and (not has_right_connectable):
                settings_port.side = "left"
            elif has_right_connectable and (not has_left_connectable):
                settings_port.side = "right"

        # Warning 侧别重判规则：
        # - 默认均视为左侧；
        # - 仅当节点标题为“多分支”，且同行（±y_tolerance）右侧存在非装饰类端口时，warning 归为右侧。
        if node_title_cn == "多分支":
            for warning_port in recognized_ports:
                if is_warning_like_port(warning_port):
                    has_right_neighbor = _has_connectable_neighbor_on_side(
                        ports=recognized_ports,
                        row_center_y=int(warning_port.center[1]),
                        side="right",
                    )
                    warning_port.side = "right" if has_right_neighbor else "left"
        else:
            for warning_port in recognized_ports:
                if is_warning_like_port(warning_port):
                    warning_port.side = "left"

        # Settings 行内装饰去重规则：
        # - 一个“可连线端口行”（同侧，同 index，同一行）最多保留一个 Settings；
        # - 若同一行命中多个 Settings 变体模板（如 Settings/Settings2），保留置信度更高者；
        #   置信度相同时：右侧取更靠右的，左侧取更靠左的。
        connectable_ports_by_side: Dict[str, List[RecognizedPort]] = {"left": [], "right": []}
        for port_obj in recognized_ports:
            if not is_connectable_like_port(port_obj):
                continue
            if port_obj.side in ("left", "right"):
                connectable_ports_by_side[port_obj.side].append(port_obj)

        def _pick_best_settings_candidate(
            *,
            existing: RecognizedPort,
            candidate: RecognizedPort,
            side: str,
        ) -> RecognizedPort:
            if float(candidate.confidence) > float(existing.confidence):
                return candidate
            if float(candidate.confidence) < float(existing.confidence):
                return existing
            existing_x = int(existing.center[0])
            candidate_x = int(candidate.center[0])
            if side == "right":
                return candidate if candidate_x > existing_x else existing
            return candidate if candidate_x < existing_x else existing

        kept_settings_by_side_and_index: Dict[Tuple[str, int], RecognizedPort] = {}
        for settings_port in [p for p in recognized_ports if is_settings_like_port(p)]:
            side_text = str(settings_port.side or "")
            if side_text not in ("left", "right"):
                continue
            row_center_y = int(settings_port.center[1])
            same_side_connectables = connectable_ports_by_side.get(side_text, [])
            best_match: Optional[RecognizedPort] = None
            best_dy: Optional[int] = None
            for neighbor in same_side_connectables:
                dy = abs(int(neighbor.center[1]) - int(row_center_y))
                if dy > y_tolerance:
                    continue
                if best_dy is None or dy < best_dy:
                    best_dy = int(dy)
                    best_match = neighbor
            if best_match is None:
                # 未能绑定到任何可连线端口行：视为噪声，不输出该 Settings
                continue
            if best_match.index is None:
                continue
            key = (side_text, int(best_match.index))
            existing = kept_settings_by_side_and_index.get(key)
            if existing is None:
                kept_settings_by_side_and_index[key] = settings_port
            else:
                kept_settings_by_side_and_index[key] = _pick_best_settings_candidate(
                    existing=existing,
                    candidate=settings_port,
                    side=side_text,
                )

        if len(kept_settings_by_side_and_index) > 0:
            settings_keep_set = set(id(obj) for obj in kept_settings_by_side_and_index.values())
            recognized_ports = [
                port_obj
                for port_obj in recognized_ports
                if (not is_settings_like_port(port_obj)) or (id(port_obj) in settings_keep_set)
            ]

        # Warning 行内装饰模板去重（仅影响普通端口识别结果）：
        # 若同一行、同一侧已存在非装饰类端口（如流程/数据端口），则在输出端口列表中隐藏该行上的 warning，
        # 避免一个物理端口在基础识别结果中同时被标记为 process 和 warning。
        # 深度端口识别依赖 TemplateMatchDebugInfo，不受本处过滤影响。
        filtered_ports: List[RecognizedPort] = []
        for port_obj in recognized_ports:
            if is_warning_like_port(port_obj):
                has_non_decorative_same_row = any(
                    (neighbor is not port_obj)
                    and (neighbor.side == port_obj.side)
                    and is_connectable_like_port(neighbor)
                    and (abs(int(neighbor.center[1]) - int(port_obj.center[1])) <= y_tolerance)
                    for neighbor in recognized_ports
                )
                if has_non_decorative_same_row:
                    continue
            filtered_ports.append(port_obj)
        recognized_ports = filtered_ports

        recognized_nodes.append(
            RecognizedNode(
                title_cn=node_title_cn,
                rect=(int(rect['x']), int(rect['y']), int(rect['width']), int(rect['height'])),
                ports=recognized_ports,
            )
        )

    return recognized_nodes







