from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from .io_utils import _cv2_imread_unicode_safe
from .models import SceneRecognizerTuning, TemplateMatchDebugInfo


_TEMPLATE_CACHE: Dict[str, Dict[str, np.ndarray]] = {}


def _load_template_images(template_dir: str) -> Dict[str, np.ndarray]:
    templates: Dict[str, np.ndarray] = {}
    template_dir_path = Path(str(template_dir))
    if not template_dir_path.exists():
        return templates
    for template_file_path in sorted(template_dir_path.iterdir(), key=lambda candidate_path: candidate_path.name.lower()):
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


def _non_maximum_suppression(
    matches: List[Dict],
    *,
    overlap_threshold: float = 0.5,
) -> Tuple[List[Dict], List[Dict]]:
    """
    对模板匹配结果执行 NMS，返回：
    - filtered：保留下来的模板命中；
    - suppressed：被抑制的模板命中（附带抑制原因与 IoU / 目标框）。
    """
    if len(matches) == 0:
        return [], []
    matches_sorted = sorted(matches, key=lambda m: m["confidence"], reverse=True)
    filtered: List[Dict] = []
    suppressed: List[Dict] = []
    for current_match in matches_sorted:
        best_iou = 0.0
        overlap_target: Optional[Dict] = None
        for kept_match in filtered:
            x1_min = current_match["x"]
            y1_min = current_match["y"]
            x1_max = x1_min + current_match["width"]
            y1_max = y1_min + current_match["height"]

            x2_min = kept_match["x"]
            y2_min = kept_match["y"]
            x2_max = x2_min + kept_match["width"]
            y2_max = y2_min + kept_match["height"]

            inter_x_min = max(x1_min, x2_min)
            inter_y_min = max(y1_min, y2_min)
            inter_x_max = min(x1_max, x2_max)
            inter_y_max = min(y1_max, y2_max)

            if inter_x_max > inter_x_min and inter_y_max > inter_y_min:
                inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
                area1 = current_match["width"] * current_match["height"]
                area2 = kept_match["width"] * kept_match["height"]
                union_area = area1 + area2 - inter_area
                if union_area <= 0:
                    continue
                iou = inter_area / union_area
                if iou > overlap_threshold and iou > best_iou:
                    best_iou = iou
                    overlap_target = kept_match

        if overlap_target is not None:
            suppressed_entry = dict(current_match)
            suppressed_entry["reason"] = "nms"
            suppressed_entry["overlap_target_bbox"] = (
                int(overlap_target["x"]),
                int(overlap_target["y"]),
                int(overlap_target["width"]),
                int(overlap_target["height"]),
            )
            suppressed_entry["iou"] = float(best_iou)
            suppressed.append(suppressed_entry)
        else:
            filtered.append(current_match)
    return filtered, suppressed


def _get_effective_template_threshold(template_name: str, base_threshold: float) -> float:
    """
    根据模板名称返回实际使用的匹配阈值。

    规则：
    - 绝大多数端口模板使用统一的 base_threshold；
    - 名称以 "process" 开头的流程端口模板（如 "Process", "Process2"）使用最小阈值 0.70；
    - 名称以 "generic" 开头的泛型端口模板（如 "Generic", "Generic2"）使用最小阈值 0.75；
    - 实际使用的阈值为 min(base_threshold, 模板最小阈值)，避免比调用方要求更严格。
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
    tuning: Optional[SceneRecognizerTuning] = None,
) -> List[Dict]:
    effective_tuning = tuning or SceneRecognizerTuning()
    rect_x = rect["x"]
    rect_y = rect["y"]
    rect_width = rect["width"]
    rect_height = rect["height"]
    header_height_for_rect = int(rect.get("header_height", header_height) or header_height)
    header_height_for_rect = max(0, min(int(header_height_for_rect), int(rect_height)))
    search_top = rect_y + header_height_for_rect
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

    matches_after_nms, suppressed_by_nms = _non_maximum_suppression(
        matches,
        overlap_threshold=float(effective_tuning.port_template_nms_iou_threshold),
    )
    rect_center_x = rect_x + rect_width / 2.0
    for match in matches_after_nms:
        match_center_x = match["x"] + match["width"] / 2.0
        match["side"] = "left" if match_center_x < rect_center_x else "right"
    for suppressed_match in suppressed_by_nms:
        match_center_x = suppressed_match["x"] + suppressed_match["width"] / 2.0
        suppressed_match["side"] = "left" if match_center_x < rect_center_x else "right"

    def is_no_index_template_name(template_name: str) -> bool:
        normalized_name = str(template_name).lower()
        return (
            normalized_name.startswith("settings")
            or normalized_name.startswith("warning")
            or normalized_name.startswith("dictionary")
        )

    y_tolerance = int(effective_tuning.port_same_row_y_tolerance_px)

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
            indexed_items = [m for m in same_row_matches if not is_no_index_template_name(m["template_name"])]
            no_index_items = [m for m in same_row_matches if is_no_index_template_name(m["template_name"])]
            if len(indexed_items) > 1:
                keeper = (
                    min(indexed_items, key=lambda m: m["x"])
                    if keep_leftmost
                    else max(indexed_items, key=lambda m: m["x"])
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
    tuning: Optional[SceneRecognizerTuning] = None,
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
        tuning,
    )
    return debug_entries



