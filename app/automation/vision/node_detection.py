# -*- coding: utf-8 -*-
"""
节点检测辅助：基于视觉识别结果与程序坐标预期，选择最合理的节点 bbox。

目的：
- 将 EditorExecutor 中的节点匹配逻辑外提，减少大文件体积；
- 保持可读阈值与调试输出结构一致。
"""

from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, List, Iterable
from PIL import Image
from app.automation.vision import list_nodes
from app.automation.input.common import compute_position_thresholds
from app.automation.vision.ocr_utils import extract_chinese

ROI_EXPANSION_FACTOR: float = 2.0

def find_best_node_bbox(
    executor,
    screenshot: Image.Image,
    title_cn: str,
    program_pos: Tuple[float, float],
    debug: Optional[Dict[str, Any]] = None,
    detected_nodes: Optional[Iterable[Any]] = None,
) -> Tuple[int, int, int, int]:
    """按“标题中文名+程序坐标就近”策略选择节点 bbox。

    返回 (x, y, w, h)；未命中返回 (0,0,0,0)。
    """
    if detected_nodes is None:
        nodes = list_nodes(screenshot)
    else:
        nodes = list(detected_nodes)
    if len(nodes) == 0:
        if debug is not None:
            debug["detected_count"] = 0
            debug["failed_reason"] = "no_detection"
        return (0, 0, 0, 0)

    # 期望位置（窗口坐标）
    expected_x, expected_y = executor.convert_program_to_editor_coords(
        program_pos[0], program_pos[1]
    )
    # 尺寸/门限（基于 scale_ratio 与程序节点尺寸 200x100）
    scale = float(executor.scale_ratio or 1.0)
    pos_threshold_px, pos_threshold_py = compute_position_thresholds(scale)
    pos_threshold_px = int(pos_threshold_px * ROI_EXPANSION_FACTOR)
    pos_threshold_py = int(pos_threshold_py * ROI_EXPANSION_FACTOR)
    # 以“期望左上角”为中心，按横纵允许误差对称扩展得到搜索范围
    roi_left = int(expected_x - pos_threshold_px)
    roi_top = int(expected_y - pos_threshold_py)
    roi_right = int(expected_x + pos_threshold_px)
    roi_bottom = int(expected_y + pos_threshold_py)

    # 若整个 ROI 与截图区域完全不相交，直接视为“当前视口外”的节点，不再回退到全局最近命中，
    # 以避免视口外的同名节点抢占当前画面中的检测结果。
    image_width, image_height = screenshot.size
    roi_completely_left = roi_right < 0
    roi_completely_right = roi_left > image_width
    roi_completely_above = roi_bottom < 0
    roi_completely_below = roi_top > image_height
    if roi_completely_left or roi_completely_right or roi_completely_above or roi_completely_below:
        if debug is not None:
            debug["failed_reason"] = "expected_out_of_view"
            debug["detected_count"] = len(nodes)
        return (0, 0, 0, 0)

    target_cn = extract_chinese(title_cn or "")
    if debug is not None:
        debug["target_cn"] = target_cn
        debug["expected_editor"] = (int(expected_x), int(expected_y))
        debug["roi"] = (
            int(roi_left),
            int(roi_top),
            int(roi_right - roi_left),
            int(roi_bottom - roi_top),
        )
        debug["pos_threshold_px"] = int(pos_threshold_px)
        debug["pos_threshold_py"] = int(pos_threshold_py)
        debug["detected_count"] = len(nodes)
        debug["in_roi_candidates"] = []
        debug["out_of_roi_named_candidates"] = []
        debug["chosen"] = None
        debug["failed_reason"] = None

    if not target_cn:
        if debug is not None:
            debug["failed_reason"] = "empty_target_cn"
        return (0, 0, 0, 0)

    def choose_best_candidate(
        primary_candidates: List[Tuple[int, float]],
        secondary_candidates: List[Tuple[int, float]],
    ) -> Tuple[int, float]:
        best_index = -1
        best_distance_square = 1e18
        for candidate_index, candidate_distance_square in primary_candidates:
            if candidate_distance_square < best_distance_square:
                best_index = candidate_index
                best_distance_square = candidate_distance_square
        if best_index >= 0:
            return best_index, best_distance_square
        for candidate_index, candidate_distance_square in secondary_candidates:
            if candidate_distance_square < best_distance_square:
                best_index = candidate_index
                best_distance_square = candidate_distance_square
        return best_index, best_distance_square

    # 收集候选：中文名匹配的 ROI 内/外元素
    roi_exact_candidates: List[Tuple[int, float]] = []
    roi_fuzzy_candidates: List[Tuple[int, float]] = []
    global_exact_candidates: List[Tuple[int, float]] = []
    global_fuzzy_candidates: List[Tuple[int, float]] = []
    out_of_roi_named: List[Tuple[int, int, int, int]] = []
    if debug is not None:
        debug["global_named_candidates"] = []
    for node_index, detected_node in enumerate(nodes):
        detected_cn = extract_chinese(str(getattr(detected_node, "name_cn", "") or ""))
        if not detected_cn:
            continue
        is_exact_match = detected_cn == target_cn
        is_substring_match = (target_cn in detected_cn) or (detected_cn in target_cn)
        if not (is_exact_match or is_substring_match):
            continue
        bbox_left, bbox_top, bbox_width, bbox_height = detected_node.bbox
        delta_x = float(bbox_left - expected_x)
        delta_y = float(bbox_top - expected_y)
        distance_square = delta_x * delta_x + delta_y * delta_y
        if is_exact_match:
            global_exact_candidates.append((node_index, distance_square))
        else:
            global_fuzzy_candidates.append((node_index, distance_square))
        if debug is not None and len(debug["global_named_candidates"]) < 10:
            debug["global_named_candidates"].append(
                {
                    "bbox": (int(bbox_left), int(bbox_top), int(bbox_width), int(bbox_height)),
                    "is_exact": bool(is_exact_match),
                    "dist2": int(distance_square),
                }
            )
        in_roi = (
            bbox_left >= roi_left
            and bbox_left <= roi_right
            and bbox_top >= roi_top
            and bbox_top <= roi_bottom
        )
        if in_roi:
            if is_exact_match:
                roi_exact_candidates.append((node_index, distance_square))
            else:
                roi_fuzzy_candidates.append((node_index, distance_square))
            if debug is not None:
                debug["in_roi_candidates"].append(
                    {
                        "bbox": (int(bbox_left), int(bbox_top), int(bbox_width), int(bbox_height)),
                        "is_exact": bool(is_exact_match),
                        "dist2": int(distance_square),
                    }
                )
        else:
            out_of_roi_named.append(
                (int(bbox_left), int(bbox_top), int(bbox_width), int(bbox_height))
            )

    if debug is not None and out_of_roi_named:
        debug["out_of_roi_named_candidates"] = out_of_roi_named[:6]

    chosen_idx, chosen_dist2 = choose_best_candidate(roi_exact_candidates, roi_fuzzy_candidates)
    threshold2 = float(pos_threshold_px * pos_threshold_px)
    fallback_needed = False
    fallback_reason = None
    if chosen_idx < 0:
        fallback_needed = True
        fallback_reason = "no_roi_candidate"
    else:
        selected_bbox = nodes[chosen_idx].bbox
        if debug is not None:
            debug["chosen"] = {
                "bbox": (
                    int(selected_bbox[0]),
                    int(selected_bbox[1]),
                    int(selected_bbox[2]),
                    int(selected_bbox[3]),
                ),
                "dist2": int(chosen_dist2),
                "threshold2": int(threshold2),
            }
        if chosen_dist2 > threshold2:
            fallback_needed = True
            fallback_reason = "distance_exceed"

    if fallback_needed:
        fallback_idx, fallback_dist2 = choose_best_candidate(
            global_exact_candidates,
            global_fuzzy_candidates,
        )
        if fallback_idx < 0:
            if debug is not None:
                debug["failed_reason"] = fallback_reason or "no_named_candidate"
            return (0, 0, 0, 0)
        fallback_bbox = nodes[fallback_idx].bbox
        if debug is not None:
            debug["fallback_used"] = True
            debug["fallback_reason"] = fallback_reason
            debug["fallback_candidate"] = {
                "bbox": (
                    int(fallback_bbox[0]),
                    int(fallback_bbox[1]),
                    int(fallback_bbox[2]),
                    int(fallback_bbox[3]),
                ),
                "dist2": int(fallback_dist2),
            }
        return (
            int(fallback_bbox[0]),
            int(fallback_bbox[1]),
            int(fallback_bbox[2]),
            int(fallback_bbox[3]),
        )

    selected_bbox = nodes[chosen_idx].bbox
    return (
        int(selected_bbox[0]),
        int(selected_bbox[1]),
        int(selected_bbox[2]),
        int(selected_bbox[3]),
    )


