# -*- coding: utf-8 -*-
"""
一步式场景识别模块：在一次图像处理流程中识别出节点矩形、节点标题与端口位置/序号。

输入：节点图画布区域的 PIL.Image（RGB）
输出：每个节点的矩形、标题（中文，仅当识别到文本时）、端口（侧别、序号、模板类型、坐标）。

注意：
- 不进行任何窗口截屏或磁盘写入，仅对传入图像进行处理；
- 不使用 try/except；错误直接抛出；
- 变量命名清晰可读，避免难以理解的缩写；
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Any
import os
import time

import cv2
import numpy as np
from PIL import Image
from app.automation.vision.ocr_utils import get_ocr_engine
from app.automation.vision.ocr_utils import extract_chinese


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


# ============================
# 基础工具
# ============================

 


def _load_template_images(template_dir: str) -> Dict[str, np.ndarray]:
    templates: Dict[str, np.ndarray] = {}
    if not os.path.exists(template_dir):
        return templates
    for filename in os.listdir(template_dir):
        if filename.lower().endswith('.png'):
            template_path = os.path.join(template_dir, filename)
            template_image = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if template_image is not None:
                template_name = os.path.splitext(filename)[0]
                templates[template_name] = template_image
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

def _match_templates_in_rectangle(screenshot: Image.Image,
                                  rect: Dict,
                                  templates: Dict[str, np.ndarray],
                                  header_height: int = 28,
                                  threshold: float = 0.7) -> List[Dict]:
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
        if search_array.shape[0] < template_height or search_array.shape[1] < template_width:
            continue
        result = cv2.matchTemplate(search_array, template_image, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)
        for pt in zip(*locations[::-1]):
            match_x = search_left + pt[0]
            match_y = search_top + pt[1]
            confidence_val = float(result[pt[1], pt[0]])
            matches.append({
                'template_name': template_name,
                'x': int(match_x),
                'y': int(match_y),
                'width': int(template_width),
                'height': int(template_height),
                'confidence': confidence_val
            })
    matches, _ = _non_maximum_suppression(matches, overlap_threshold=0.5)
    rect_center_x = rect_x + rect_width / 2.0
    for match in matches:
        match_center_x = match['x'] + match['width'] / 2.0
        match['side'] = 'left' if match_center_x < rect_center_x else 'right'
    # 非索引类模板（装饰项）：不参与同行去重
    # - settings / warning：本来就不需要索引
    # - dictionary：与 settings 归为同一类装饰控件，不做同行去重
    no_index_templates = ['settings', 'warning', 'dictionary']
    # 同行容差（像素）
    y_tolerance = 10

    left_matches = sorted([m for m in matches if m['side'] == 'left'], key=lambda m: m['y'])
    right_matches = sorted([m for m in matches if m['side'] == 'right'], key=lambda m: m['y'])

    def filter_same_row_ports(side_matches: List[Dict], keep_leftmost: bool) -> List[Dict]:
        if len(side_matches) == 0:
            return []
        filtered: List[Dict] = []
        index_val = 0
        i = 0
        while i < len(side_matches):
            current = side_matches[i]
            same_row_list = [current]
            j = i + 1
            while j < len(side_matches):
                if abs(side_matches[j]['y'] - current['y']) <= y_tolerance:
                    same_row_list.append(side_matches[j])
                    j += 1
                else:
                    break
            indexed_items = [m for m in same_row_list if m['template_name'].lower() not in no_index_templates]
            no_index_items = [m for m in same_row_list if m['template_name'].lower() in no_index_templates]
            if len(indexed_items) > 1:
                keeper = min(indexed_items, key=lambda m: m['x']) if keep_leftmost else max(indexed_items, key=lambda m: m['x'])
                keeper['index'] = index_val
                index_val += 1
                filtered.append(keeper)
            elif len(indexed_items) == 1:
                indexed_items[0]['index'] = index_val
                index_val += 1
                filtered.append(indexed_items[0])
            for item in no_index_items:
                item['index'] = None
                filtered.append(item)
            i = j
        return filtered

    left_matches = filter_same_row_ports(left_matches, keep_leftmost=True)
    right_matches = filter_same_row_ports(right_matches, keep_leftmost=False)
    left_matches.sort(key=lambda m: m['y'])
    right_matches.sort(key=lambda m: m['y'])
    return left_matches + right_matches


# ============================
# 主流程
# ============================

def _detect_rectangles_from_canvas(canvas_image: Image.Image) -> List[Dict]:
    # 与 color_block_detector.py 相同的步骤：HSV双掩码 → 形态学 → 双向扫描去飞线 → 轮廓 → 合并
    print("\n" + "=" * 60)
    print("检测鲜亮色块（画布内）")
    print("=" * 60)

    # 输出目录（与 color_block_detector 一致）
    output_dir = r"E:\Dep\UGC\testimage"
    debug_dir = os.path.join(output_dir, "debug_steps")
    os.makedirs(debug_dir, exist_ok=True)
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
    step1_path = os.path.join(debug_dir, f"{timestamp}_step1_color_mask_raw.png")
    cv2.imwrite(step1_path, mask_colorful)
    step2_path = os.path.join(debug_dir, f"{timestamp}_step2_white_mask_raw.png")
    cv2.imwrite(step2_path, mask_white)

    # 形态学（分别处理后合并）
    kernel_close_color = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    kernel_close_white = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask_colorful = _apply_morphology_operations(mask_colorful, kernel_close_color, kernel_open, 2, 1)
    mask_white = _apply_morphology_operations(mask_white, kernel_close_white, kernel_open, 1, 1)
    step3_path = os.path.join(debug_dir, f"{timestamp}_step3_color_mask_morphed.png")
    cv2.imwrite(step3_path, mask_colorful)
    step4_path = os.path.join(debug_dir, f"{timestamp}_step4_white_mask_morphed.png")
    cv2.imwrite(step4_path, mask_white)

    mask_bright = cv2.bitwise_or(mask_colorful, mask_white)
    step5_path = os.path.join(debug_dir, f"{timestamp}_step5_merged_mask.png")
    cv2.imwrite(step5_path, mask_bright)

    # 直接进入双向扫描去飞线
    mask_filtered = mask_bright
    step6_path = os.path.join(debug_dir, f"{timestamp}_step6_prescan_mask.png")
    cv2.imwrite(step6_path, mask_filtered)

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
    step7_path = os.path.join(debug_dir, f"{timestamp}_step7_vertical_scan.png")
    cv2.imwrite(step7_path, mask_no_lines)

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
    step8_path = os.path.join(debug_dir, f"{timestamp}_step8_horizontal_scan.png")
    cv2.imwrite(step8_path, mask_no_lines_h)

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

        def is_non_decorative_port(port_obj: RecognizedPort) -> bool:
            kind_lower = port_obj.kind.lower()
            return kind_lower not in ("settings", "warning")

        # Settings 侧别重判规则：
        # - 识别为右侧的 Settings 行，如果同行（±y_tolerance）右侧不存在任何非装饰类端口，
        #   但左侧存在非装饰类端口，则将该 Settings 强制归为左侧。
        for settings_port in recognized_ports:
            if settings_port.kind.lower() != "settings":
                continue
            if settings_port.side != "right":
                continue
            has_right_data_or_flow = any(
                (neighbor.side == "right")
                and is_non_decorative_port(neighbor)
                and (abs(int(neighbor.center[1]) - int(settings_port.center[1])) <= y_tolerance)
                for neighbor in recognized_ports
            )
            if has_right_data_or_flow:
                continue
            has_left_data_or_flow = any(
                (neighbor.side == "left")
                and is_non_decorative_port(neighbor)
                and (abs(int(neighbor.center[1]) - int(settings_port.center[1])) <= y_tolerance)
                for neighbor in recognized_ports
            )
            if has_left_data_or_flow:
                settings_port.side = "left"

        # Warning 侧别重判规则：
        # - 默认均视为左侧；
        # - 仅当节点标题为“多分支”，且同行（±y_tolerance）右侧存在非装饰类端口时，warning 归为右侧。
        if node_title_cn == "多分支":
            for warning_port in recognized_ports:
                if warning_port.kind.lower() == "warning":
                    has_right_neighbor = any(
                        (neighbor.side == "right")
                        and is_non_decorative_port(neighbor)
                        and (abs(int(neighbor.center[1]) - int(warning_port.center[1])) <= y_tolerance)
                        for neighbor in recognized_ports
                    )
                    warning_port.side = "right" if has_right_neighbor else "left"
        else:
            for warning_port in recognized_ports:
                if warning_port.kind.lower() == "warning":
                    warning_port.side = "left"

        recognized_nodes.append(
            RecognizedNode(
                title_cn=node_title_cn,
                rect=(int(rect['x']), int(rect['y']), int(rect['width']), int(rect['height'])),
                ports=recognized_ports,
            )
        )

    return recognized_nodes







