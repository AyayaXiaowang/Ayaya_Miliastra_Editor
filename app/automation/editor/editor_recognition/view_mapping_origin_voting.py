# -*- coding: utf-8 -*-
"""
editor_recognition.view_mapping_origin_voting

固定缩放比例(1.0)下的原点平移投票：
- 基于“检测 bbox 左上角 - 程序坐标”生成平移样本
- 网格聚类得到若干候选 origin
- 在候选 origin 下评估匹配数量与缺失惩罚，选出最佳 origin
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .models import MappingData


# ===== 原点平移投票相关常量 =====

ORIGIN_VOTING_BIN_SIZE_X: float = 80.0
ORIGIN_VOTING_BIN_SIZE_Y: float = 40.0
ORIGIN_VOTING_MAX_TITLES: int = 120
ORIGIN_VOTING_MAX_MODELS_PER_TITLE: int = 32
ORIGIN_VOTING_MAX_DETECTIONS_PER_TITLE: int = 32
ORIGIN_VOTING_MAX_EVAL_MODELS_PER_TITLE: int = 64
ORIGIN_VOTING_MAX_EVAL_DETECTIONS_PER_TITLE: int = 64
ORIGIN_VOTING_MAX_CANDIDATES: int = 8
ORIGIN_VOTING_POSITION_TOL_MULTIPLIER: float = 0.75
ORIGIN_VOTING_MIN_INLIERS: int = 4
ORIGIN_VOTING_MISSING_PENALTY: float = 0.5


def _generate_origin_samples(mappings: MappingData) -> list[tuple[float, float]]:
    """
    在固定缩放比例为 1.0 的前提下，为所有“模型节点-检测框”对生成原点平移样本。

    原点样本含义：origin ≈ detection_left_top - program_pos
    """
    origin_samples: list[tuple[float, float]] = []
    shared_names = list(mappings.shared_names)
    if len(shared_names) > ORIGIN_VOTING_MAX_TITLES:
        shared_names = shared_names[:ORIGIN_VOTING_MAX_TITLES]

    for title in shared_names:
        model_nodes = mappings.name_to_model_nodes.get(title, [])
        detection_bboxes = mappings.name_to_detections.get(title, [])
        if not model_nodes or not detection_bboxes:
            continue

        limited_models = model_nodes[:ORIGIN_VOTING_MAX_MODELS_PER_TITLE]
        limited_detections = detection_bboxes[:ORIGIN_VOTING_MAX_DETECTIONS_PER_TITLE]

        for model in limited_models:
            program_x = float(model.pos[0])
            program_y = float(model.pos[1])
            for bbox in limited_detections:
                bbox_left = float(bbox[0])
                bbox_top = float(bbox[1])
                origin_x = bbox_left - program_x
                origin_y = bbox_top - program_y
                origin_samples.append((origin_x, origin_y))

    return origin_samples


def _cluster_origin_samples(origin_samples: list[tuple[float, float]]) -> list[tuple[float, float, int]]:
    """
    使用网格聚类原点样本，返回若干候选原点 (origin_x, origin_y, vote_count)。
    """
    if not origin_samples:
        return []

    bins: Dict[tuple[int, int], Dict[str, float]] = {}
    bin_width = float(ORIGIN_VOTING_BIN_SIZE_X)
    bin_height = float(ORIGIN_VOTING_BIN_SIZE_Y)

    for origin_x, origin_y in origin_samples:
        bin_x = int(origin_x / bin_width)
        bin_y = int(origin_y / bin_height)
        key = (bin_x, bin_y)
        if key not in bins:
            bins[key] = {"count": 0.0, "sum_x": 0.0, "sum_y": 0.0}
        bucket = bins[key]
        bucket["count"] = float(bucket["count"]) + 1.0
        bucket["sum_x"] = float(bucket["sum_x"]) + float(origin_x)
        bucket["sum_y"] = float(bucket["sum_y"]) + float(origin_y)

    sorted_bins = sorted(bins.items(), key=lambda item: item[1]["count"], reverse=True)
    if ORIGIN_VOTING_MAX_CANDIDATES > 0 and len(sorted_bins) > ORIGIN_VOTING_MAX_CANDIDATES:
        sorted_bins = sorted_bins[:ORIGIN_VOTING_MAX_CANDIDATES]

    candidates: list[tuple[float, float, int]] = []
    for (_bin_x, _bin_y), bucket in sorted_bins:
        count_value = int(bucket["count"])
        if count_value <= 0:
            continue
        average_x = float(bucket["sum_x"]) / float(bucket["count"])
        average_y = float(bucket["sum_y"]) / float(bucket["count"])
        candidates.append((average_x, average_y, count_value))

    return candidates


def _evaluate_origin_candidate(
    executor,
    mappings: MappingData,
    origin_x: float,
    origin_y: float,
    region_rect: Optional[tuple[int, int, int, int]],
    position_tolerance_x: float,
    position_tolerance_y: float,
) -> dict[str, Any]:
    """
    在给定原点平移下，统计可解释的检测数量与“理论上应可见但未匹配”的节点数量。
    """
    matched_detections = 0
    total_detections = 0
    missing_expected_nodes = 0

    for title in mappings.shared_names:
        model_nodes = mappings.name_to_model_nodes.get(title, [])
        detection_bboxes = mappings.name_to_detections.get(title, [])
        if not model_nodes or not detection_bboxes:
            continue

        limited_models = model_nodes[:ORIGIN_VOTING_MAX_EVAL_MODELS_PER_TITLE]
        limited_detections = detection_bboxes[:ORIGIN_VOTING_MAX_EVAL_DETECTIONS_PER_TITLE]

        total_detections += len(limited_detections)

        used_model_ids: set[str] = set()
        for bbox in limited_detections:
            bbox_left = float(bbox[0])
            bbox_top = float(bbox[1])
            best_error_value: Optional[float] = None
            best_model_id: str | None = None
            for model in limited_models:
                model_id = getattr(model, "id", "")
                if not model_id or model_id in used_model_ids:
                    continue
                expected_x = origin_x + float(model.pos[0])
                expected_y = origin_y + float(model.pos[1])
                delta_x = abs(bbox_left - expected_x)
                delta_y = abs(bbox_top - expected_y)
                if delta_x > position_tolerance_x or delta_y > position_tolerance_y:
                    continue
                error_value = float(delta_x + delta_y)
                if best_error_value is None or error_value < best_error_value:
                    best_error_value = error_value
                    best_model_id = model_id
            if best_model_id is not None:
                used_model_ids.add(best_model_id)
                matched_detections += 1

        if region_rect is not None:
            region_x, region_y, region_width, region_height = region_rect
            region_right = int(region_x + region_width)
            region_bottom = int(region_y + region_height)
            for model in limited_models:
                model_id = getattr(model, "id", "")
                if not model_id or model_id in used_model_ids:
                    continue
                expected_x = origin_x + float(model.pos[0])
                expected_y = origin_y + float(model.pos[1])
                inside_horizontal = bool(expected_x >= float(region_x) and expected_x <= float(region_right))
                inside_vertical = bool(expected_y >= float(region_y) and expected_y <= float(region_bottom))
                if inside_horizontal and inside_vertical:
                    missing_expected_nodes += 1

    score_value = float(matched_detections) - float(missing_expected_nodes) * float(
        ORIGIN_VOTING_MISSING_PENALTY
    )
    return {
        "matched": int(matched_detections),
        "total_detections": int(total_detections),
        "missing": int(missing_expected_nodes),
        "score": score_value,
    }


