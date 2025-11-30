# -*- coding: utf-8 -*-
"""
editor_recognition.recognition

高层入口：截图预热、节点可见性检测与视口映射校验。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from pathlib import Path
from PIL import Image
import math
from statistics import median

from app.automation import capture as editor_capture
from app.automation.input.common import build_graph_region_overlay, compute_position_thresholds
from app.automation.vision import invalidate_cache, list_nodes
from engine.graph.models.graph_model import GraphModel
from app.automation.core.editor_mapping import FIXED_SCALE_RATIO
from .constants import (
    FIT_STRATEGY_ORIGIN_TRANSLATION,
    FIT_STRATEGY_ORDINARY_NODES,
    FIT_STRATEGY_RELATIVE_ANCHORS,
    ORDINARY_NODES_MIN_MATCHES,
    ORDINARY_NODES_POSITION_TOLERANCE_MULTIPLIER,
    RELATIVE_ANCHOR_MAX_ANISOTROPY,
    RELATIVE_ANCHOR_MIN_MATCHES,
    RELATIVE_ANCHOR_MIN_PROG_DELTA,
    RELATIVE_ANCHOR_TOLERANCE_MULTIPLIER,
    RELATIVE_ANCHOR_MAX_NEIGHBORS,
    UNIQUE_RATIO_TOLERANCE,
)
from .logging_utils import log_detection_snapshot
from .mappings import build_detection_mappings
from .models import MappingData, ViewMappingFitResult


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


def prepare_for_connect(executor, log_callback=None) -> None:
    screenshot = editor_capture.capture_window(executor.window_title)
    if screenshot:
        invalidate_cache()
        detected = list_nodes(screenshot)
        # 将本次识别结果注入场景快照，便于后续步骤在视口未变化时复用
        get_scene_snapshot = getattr(executor, "get_scene_snapshot", None)
        if callable(get_scene_snapshot) and bool(
            getattr(executor, "enable_scene_snapshot_optimization", True)
        ):
            scene_snapshot = get_scene_snapshot()
            update_method = getattr(scene_snapshot, "update_from_detection", None)
            if callable(update_method):
                update_method(screenshot, detected)


def _build_detection_centers_by_title(mappings: MappingData) -> Dict[str, list[dict[str, Any]]]:
    """
    将检测框按中文标题分组，并为每个检测记录一个“对齐基准点”。

    约定：
    - 统一以 **节点左上角(bbox_x, bbox_y)** 作为坐标基准，而不是中心点。
    - 这样可以与 GraphModel.NodeModel.pos 的语义保持一致（均为左上角），
      避免在视口拟合与创建节点时出现“程序坐标认为在右侧，视觉上反而在左侧”的偏差。
    """
    centers_by_title: Dict[str, list[dict[str, Any]]] = {}
    for name, detections in mappings.name_to_detections.items():
        centers: list[dict[str, Any]] = []
        for bbox in detections:
            bbox_x, bbox_y, bbox_w, bbox_h = bbox
            # 统一使用左上角作为锚点，保持与 NodeModel.pos 的含义一致
            anchor_x = float(bbox_x)
            anchor_y = float(bbox_y)
            centers.append({"bbox": bbox, "anchor": (anchor_x, anchor_y)})
        if centers:
            centers_by_title[name] = centers
    return centers_by_title


def _compute_global_centers(
    mappings: MappingData,
    centers_by_title: Dict[str, list[dict[str, Any]]],
) -> tuple[tuple[float, float], tuple[float, float]]:
    prog_sum_x = 0.0
    prog_sum_y = 0.0
    prog_count = 0
    for nodes in mappings.name_to_model_nodes.values():
        for node in nodes:
            prog_sum_x += float(node.pos[0])
            prog_sum_y += float(node.pos[1])
            prog_count += 1
    det_sum_x = 0.0
    det_sum_y = 0.0
    det_count = 0
    for centers in centers_by_title.values():
        for item in centers:
            det_sum_x += float(item["anchor"][0])
            det_sum_y += float(item["anchor"][1])
            det_count += 1
    prog_center = (prog_sum_x / prog_count, prog_sum_y / prog_count) if prog_count > 0 else (0.0, 0.0)
    det_center = (det_sum_x / det_count, det_sum_y / det_count) if det_count > 0 else (0.0, 0.0)
    return prog_center, det_center


def _flatten_model_nodes(mappings: MappingData) -> list[dict[str, Any]]:
    all_nodes: list[dict[str, Any]] = []
    for title, nodes in mappings.name_to_model_nodes.items():
        for node in nodes:
            all_nodes.append({"node": node, "title": title})
    return all_nodes


def _dump_last_focus_detection_snapshot(
    executor,
    graph_model: GraphModel,
    detected: list,
) -> None:
    """
    将最近一次用于视口拟合的原始检测结果落盘为 JSON，便于离线分析。

    仅包含“截图中识别到的节点名字与坐标”，不涉及模型 node_id：
    - 路径：{workspace_root}/runtime/cache/last_focus_detection.json
    - 字段：graph_id、每个检测框的中文标题与编辑器坐标 bbox。
    """
    workspace_path_value = getattr(executor, "workspace_path", None)
    if workspace_path_value is None:
        return
    base_path = Path(workspace_path_value)
    output_dir = base_path / "runtime" / "cache"
    output_dir.mkdir(parents=True, exist_ok=True)

    graph_id_value = getattr(graph_model, "graph_id", None)
    graph_id_text = str(graph_id_value) if graph_id_value is not None else ""

    detections_payload: list[dict] = []
    for detection in detected:
        bbox_x, bbox_y, bbox_w, bbox_h = detection.bbox
        raw_name_cn = str(getattr(detection, "name_cn", "") or "")
        title_cn = ""
        if hasattr(executor, "_extract_chinese"):
            title_cn = executor._extract_chinese(raw_name_cn)
        detections_payload.append(
            {
                "title_cn": title_cn,
                "raw_name_cn": raw_name_cn,
                "bbox": [
                    int(bbox_x),
                    int(bbox_y),
                    int(bbox_w),
                    int(bbox_h),
                ],
            }
        )

    payload = {
        "graph_id": graph_id_text,
        "detected_count": int(len(detections_payload)),
        "detections": detections_payload,
    }

    output_path = output_dir / "last_focus_detection.json"
    with output_path.open("w", encoding="utf-8") as f:
        import json

        json.dump(payload, f, ensure_ascii=False, indent=2)


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


def _collect_neighbor_models(
    anchor_model,
    all_model_nodes: list[dict[str, Any]],
    centers_by_title: Dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    neighbors: list[tuple[float, dict[str, Any]]] = []
    anchor_x = float(anchor_model.pos[0])
    anchor_y = float(anchor_model.pos[1])
    for candidate in all_model_nodes:
        node = candidate["node"]
        if node is anchor_model:
            continue
        title = candidate["title"]
        if title not in centers_by_title:
            continue
        dx = float(node.pos[0]) - anchor_x
        dy = float(node.pos[1]) - anchor_y
        dist2 = dx * dx + dy * dy
        if dist2 <= 0.1:
            continue
        neighbors.append((dist2, candidate))
    neighbors.sort(key=lambda item: item[0])
    trimmed: list[dict[str, Any]] = []
    for _, candidate in neighbors:
        trimmed.append(candidate)
        if len(trimmed) >= RELATIVE_ANCHOR_MAX_NEIGHBORS:
            break
    return trimmed


def _is_ratio_consistent(value: float, samples: list[float]) -> bool:
    if not samples:
        return True
    ref = median(samples)
    max_ref = max(abs(ref), 0.01)
    return abs(value - ref) <= UNIQUE_RATIO_TOLERANCE * max_ref


def _compute_scale_from_samples(
    scale_x_samples: list[float],
    scale_y_samples: list[float],
) -> Optional[tuple[float, float, float]]:
    scale_x = median(scale_x_samples) if scale_x_samples else None
    scale_y = median(scale_y_samples) if scale_y_samples else None
    if scale_x is None and scale_y is None:
        return None
    if scale_x is None:
        scale_x = scale_y
    if scale_y is None:
        scale_y = scale_x
    if scale_x is None or scale_y is None:
        return None
    if abs(scale_x) <= 1e-6 or abs(scale_y) <= 1e-6:
        return None
    anisotropy = abs(scale_x - scale_y) / max((abs(scale_x) + abs(scale_y)) * 0.5, 1e-6)
    if anisotropy > RELATIVE_ANCHOR_MAX_ANISOTROPY:
        return None
    scale = float((scale_x + scale_y) * 0.5)
    return float(scale), float(scale_x), float(scale_y)


def _select_detection_for_neighbor(
    anchor_model,
    neighbor_model,
    neighbor_title: str,
    centers_by_title: Dict[str, list[dict[str, Any]]],
    anchor_center: tuple[float, float],
    scale_x_samples: list[float],
    scale_y_samples: list[float],
) -> Optional[tuple[dict[str, Any], Optional[float], Optional[float]]]:
    detections = centers_by_title.get(neighbor_title, [])
    if not detections:
        return None
    anchor_x, anchor_y = anchor_center
    dx_prog = float(neighbor_model.pos[0]) - float(anchor_model.pos[0])
    dy_prog = float(neighbor_model.pos[1]) - float(anchor_model.pos[1])
    if abs(dx_prog) < RELATIVE_ANCHOR_MIN_PROG_DELTA and abs(dy_prog) < RELATIVE_ANCHOR_MIN_PROG_DELTA:
        return None
    selected = None
    selected_ratios: tuple[Optional[float], Optional[float]] = (None, None)
    for detection in detections:
        det_x, det_y = detection["anchor"]
        if det_x == anchor_x and det_y == anchor_y:
            continue
        ratio_x = None
        ratio_y = None
        if abs(dx_prog) >= RELATIVE_ANCHOR_MIN_PROG_DELTA:
            ratio_x = (det_x - anchor_x) / dx_prog
            if not math.isfinite(ratio_x):
                ratio_x = None
        if abs(dy_prog) >= RELATIVE_ANCHOR_MIN_PROG_DELTA:
            ratio_y = (det_y - anchor_y) / dy_prog
            if not math.isfinite(ratio_y):
                ratio_y = None
        if ratio_x is None and ratio_y is None:
            continue
        ratio_ok = True
        if ratio_x is not None and not _is_ratio_consistent(ratio_x, scale_x_samples):
            ratio_ok = False
        if ratio_y is not None and not _is_ratio_consistent(ratio_y, scale_y_samples):
            ratio_ok = False
        if not ratio_ok:
            continue
        selected = detection
        selected_ratios = (ratio_x, ratio_y)
        break
    if selected is None:
        return None
    return selected, selected_ratios[0], selected_ratios[1]
def _evaluate_transform_support(
    mappings: MappingData,
    centers_by_title: Dict[str, list[dict[str, Any]]],
    scale_x: float,
    scale_y: float,
    offset_x: float,
    offset_y: float,
    tolerance_multiplier: float,
) -> dict[str, Any]:
    avg_scale = max((abs(scale_x) + abs(scale_y)) * 0.5, 1e-6)
    tolerance_x, tolerance_y = compute_position_thresholds(avg_scale)
    tolerance_x *= tolerance_multiplier
    tolerance_y *= tolerance_multiplier
    matched = 0
    total = 0
    matches_detail: list[dict[str, Any]] = []
    for name in mappings.shared_names:
        detections = centers_by_title.get(name, [])
        models = mappings.name_to_model_nodes.get(name, [])
        if not detections or not models:
            continue
        total += len(detections)
        used_model_ids: set[str] = set()
        for detection in detections:
            center_x, center_y = detection["anchor"]
            best_model = None
            best_err = None
            best_dx = 0.0
            best_dy = 0.0
            best_expected_x = 0.0
            best_expected_y = 0.0
            for model in models:
                model_id = getattr(model, "id", None)
                if model_id in used_model_ids:
                    continue
                expected_x = scale_x * float(model.pos[0]) + offset_x
                expected_y = scale_y * float(model.pos[1]) + offset_y
                dx = abs(center_x - expected_x)
                dy = abs(center_y - expected_y)
                if dx <= tolerance_x and dy <= tolerance_y:
                    combined_err = dx + dy
                    if best_err is None or combined_err < best_err:
                        best_err = combined_err
                        best_model = model
                        best_dx = dx
                        best_dy = dy
                        best_expected_x = expected_x
                        best_expected_y = expected_y
            if best_model is not None:
                matched += 1
                model_id = getattr(best_model, "id", None)
                if model_id is not None:
                    used_model_ids.add(model_id)
                matches_detail.append(
                    {
                        "title": name,
                        "model_id": model_id or "",
                        "node": best_model,
                        "model_pos": (float(best_model.pos[0]), float(best_model.pos[1])),
                        "expected_center": (best_expected_x, best_expected_y),
                        "detection_center": (center_x, center_y),
                        "error": (best_dx, best_dy),
                    }
                )
    ratio = float(matched) / float(total) if total > 0 else 0.0
    return {
        "matched": matched,
        "total": total,
        "ratio": ratio,
        "matches": matches_detail,
        "tolerance": (tolerance_x, tolerance_y),
    }


def _try_relative_anchor_alignment(
    executor,
    mappings: MappingData,
    prefer_unique: bool,
    log_callback,
) -> Optional[ViewMappingFitResult]:
    centers_by_title = _build_detection_centers_by_title(mappings)
    if not centers_by_title:
        executor._log("[相对匹配] 当前画面无可用检测节点", log_callback)
        return None
    all_model_nodes = _flatten_model_nodes(mappings)
    if not all_model_nodes:
        executor._log("[相对匹配] 模型节点为空", log_callback)
        return None
    prog_center, _ = _compute_global_centers(mappings, centers_by_title)
    anchor_candidates: list[dict[str, Any]] = []
    for name in mappings.shared_names:
        models = mappings.name_to_model_nodes.get(name, [])
        detections = centers_by_title.get(name, [])
        if not models or not detections:
            continue
        is_unique = len(models) == 1 and len(detections) == 1
        if prefer_unique and not is_unique:
            continue
        for model in models:
            dx = float(model.pos[0]) - prog_center[0]
            dy = float(model.pos[1]) - prog_center[1]
            anchor_candidates.append(
                {
                    "name": name,
                    "model": model,
                    "detections": detections,
                    "dist2": dx * dx + dy * dy,
                    "is_unique": is_unique,
                }
            )
    if not anchor_candidates:
        if prefer_unique:
            executor._log("[相对匹配] 未找到唯一标题锚点，转为普通节点", log_callback)
        else:
            executor._log("[相对匹配] 无可用锚点候选", log_callback)
        return None
    anchor_candidates.sort(key=lambda item: item["dist2"])
    best_choice: Optional[dict[str, Any]] = None
    for candidate in anchor_candidates:
        anchor_model = candidate["model"]
        neighbors = _collect_neighbor_models(anchor_model, all_model_nodes, centers_by_title)
        if not neighbors:
            continue
        for detection in candidate["detections"]:
            anchor_center = detection["anchor"]
            scale_x_samples: list[float] = []
            scale_y_samples: list[float] = []
            matched_neighbors = 0
            for neighbor in neighbors:
                neighbor_model = neighbor["node"]
                neighbor_title = neighbor["title"]
                selection = _select_detection_for_neighbor(
                    anchor_model,
                    neighbor_model,
                    neighbor_title,
                    centers_by_title,
                    anchor_center,
                    scale_x_samples,
                    scale_y_samples,
                )
                if selection is None:
                    continue
                _, ratio_x, ratio_y = selection
                if ratio_x is not None:
                    scale_x_samples.append(ratio_x)
                if ratio_y is not None:
                    scale_y_samples.append(ratio_y)
                matched_neighbors += 1
                if matched_neighbors >= RELATIVE_ANCHOR_MAX_NEIGHBORS:
                    break
            if matched_neighbors < RELATIVE_ANCHOR_MIN_MATCHES:
                continue
            scale_tuple = _compute_scale_from_samples(scale_x_samples, scale_y_samples)
            if scale_tuple is None:
                continue
            scale_avg, scale_x_val, scale_y_val = scale_tuple
            anchor_x, anchor_y = anchor_center
            offset_x = anchor_x - scale_x_val * float(anchor_model.pos[0])
            offset_y = anchor_y - scale_y_val * float(anchor_model.pos[1])
            support = _evaluate_transform_support(
                mappings,
                centers_by_title,
                scale_x_val,
                scale_y_val,
                offset_x,
                offset_y,
                RELATIVE_ANCHOR_TOLERANCE_MULTIPLIER,
            )
            if support["matched"] < RELATIVE_ANCHOR_MIN_MATCHES:
                continue
            if best_choice is None or support["matched"] > best_choice["support"]["matched"] or (
                support["matched"] == best_choice["support"]["matched"]
                and support["ratio"] > best_choice["support"]["ratio"]
            ):
                best_choice = {
                    "scale": scale_avg,
                    "scale_x": scale_x_val,
                    "scale_y": scale_y_val,
                    "tx": offset_x,
                    "ty": offset_y,
                    "support": support,
                    "anchor_name": candidate["name"],
                }
                if support["matched"] >= max(RELATIVE_ANCHOR_MIN_MATCHES + 1, 3):
                    break
        if best_choice is not None:
            break
    if best_choice is None:
        executor._log(
            "[相对匹配] 未找到满足邻域匹配条件的锚点" + ("（唯一模式）" if prefer_unique else ""),
            log_callback,
        )
        return None

    measured_scale = float(best_choice["scale"])

    # 在最终提交映射时，比例仍固定为 1:1，仅根据匹配结果在该比例下重新估算 origin；
    # 这样可以避免将缩放估计值直接叠加到平移上导致的远端节点大幅偏移。
    origin_x = int(round(best_choice["tx"]))
    origin_y = int(round(best_choice["ty"]))
    matches_for_origin = best_choice["support"].get("matches") or []
    if matches_for_origin:
        origin_samples_x: list[float] = []
        origin_samples_y: list[float] = []
        for record in matches_for_origin:
            model_pos = record.get("model_pos")
            det_center = record.get("detection_center")
            if not model_pos or not det_center:
                continue
            prog_x, prog_y = float(model_pos[0]), float(model_pos[1])
            det_x, det_y = float(det_center[0]), float(det_center[1])
            # 在固定 scale_ratio=1.0 的约定下，直接用“检测中心 - 程序坐标”估算平移项
            origin_samples_x.append(det_x - prog_x * FIXED_SCALE_RATIO)
            origin_samples_y.append(det_y - prog_y * FIXED_SCALE_RATIO)
        if origin_samples_x and origin_samples_y:
            origin_x = int(round(median(origin_samples_x)))
            origin_y = int(round(median(origin_samples_y)))

    executor.scale_ratio = FIXED_SCALE_RATIO
    executor.origin_node_pos = (origin_x, origin_y)
    matched = best_choice["support"]["matched"]
    total = best_choice["support"]["total"]
    ratio = best_choice["support"]["ratio"]
    tol_x, tol_y = best_choice["support"]["tolerance"]
    executor._log(
        f"[相对匹配] 锚点 '{best_choice['anchor_name']}'：命中 {matched}/{total} ({ratio:.2f}) "
        f"scale_est=({best_choice['scale_x']:.4f},{best_choice['scale_y']:.4f}) avg≈{measured_scale:.4f}→固定 {executor.scale_ratio:.2f} "
        f"origin=({executor.origin_node_pos[0]},{executor.origin_node_pos[1]}) "
        f"容差=({tol_x:.1f},{tol_y:.1f})px",
        log_callback,
    )
    if best_choice["support"]["matches"]:
        preview = best_choice["support"]["matches"][:5]
        for idx, match in enumerate(preview, start=1):
            err_x, err_y = match["error"]
            executor._log(
                f"    · 匹配{idx}: '{match['title']}' exp={match['expected_center']} det={match['detection_center']} "
                f"err=({err_x:.1f},{err_y:.1f})",
                log_callback,
            )
    _update_position_delta_cache_from_matches(
        executor,
        best_choice["support"].get("matches", []),
        best_choice["scale_x"],
        best_choice["scale_y"],
        best_choice["tx"],
        best_choice["ty"],
    )
    return ViewMappingFitResult(success=True, strategy=FIT_STRATEGY_RELATIVE_ANCHORS)


def _try_ordinary_nodes_position_match(
    executor,
    mappings: MappingData,
    log_callback,
) -> Optional[ViewMappingFitResult]:
    """
    普通节点坐标匹配兜底逻辑：
    当唯一节点不足时，遍历所有共享节点，对比程序坐标与检测坐标的匹配程度。
    """
    if executor.scale_ratio is None or executor.origin_node_pos is None:
        executor._log("[普通节点] 坐标未校准，无法进行位置匹配", log_callback)
        return None
    
    scale_ratio = float(executor.scale_ratio)
    origin_x = float(executor.origin_node_pos[0])
    origin_y = float(executor.origin_node_pos[1])
    
    pos_threshold_x, pos_threshold_y = compute_position_thresholds(scale_ratio)
    pos_threshold_x *= ORDINARY_NODES_POSITION_TOLERANCE_MULTIPLIER
    pos_threshold_y *= ORDINARY_NODES_POSITION_TOLERANCE_MULTIPLIER
    
    executor._log(
        f"[普通节点] 开始位置匹配：scale={scale_ratio:.4f} origin=({origin_x:.1f},{origin_y:.1f}) "
        f"容差=({pos_threshold_x:.1f},{pos_threshold_y:.1f})px",
        log_callback,
    )
    
    matched_nodes: list[tuple[str, float, float, float, float, float]] = []
    
    for name in mappings.shared_names:
        models = mappings.name_to_model_nodes.get(name, [])
        detections = mappings.name_to_detections.get(name, [])
        
        if not models or not detections:
            continue
        
        for model in models:
            prog_x = float(model.pos[0])
            prog_y = float(model.pos[1])
            
            expected_x = origin_x + prog_x * scale_ratio
            expected_y = origin_y + prog_y * scale_ratio
            
            for detection in detections:
                det_left = float(detection[0])
                det_top = float(detection[1])
                
                delta_x = abs(det_left - expected_x)
                delta_y = abs(det_top - expected_y)
                
                if delta_x <= pos_threshold_x and delta_y <= pos_threshold_y:
                    matched_nodes.append((name, prog_x, prog_y, det_left, det_top, 
                                         (delta_x * delta_x + delta_y * delta_y) ** 0.5))
                    executor._log(
                        f"  [匹配{len(matched_nodes)}] '{name}': prog=({prog_x:.1f},{prog_y:.1f}) "
                        f"→ 预期=({expected_x:.1f},{expected_y:.1f}) vs 检测=({det_left:.1f},{det_top:.1f}) "
                        f"偏差=({delta_x:.1f},{delta_y:.1f})px",
                        log_callback,
                    )
                    break
    
    executor._log(
        f"[普通节点] 匹配完成：共匹配 {len(matched_nodes)} 个节点（需要≥{ORDINARY_NODES_MIN_MATCHES}）",
        log_callback,
    )
    
    if len(matched_nodes) >= ORDINARY_NODES_MIN_MATCHES:
        executor._log(
            f"✓ 普通节点位置匹配成功：{len(matched_nodes)} 个节点匹配，视口校准完成",
            log_callback,
        )
        return ViewMappingFitResult(success=True, strategy=FIT_STRATEGY_ORDINARY_NODES)
    
    executor._log(
        f"✗ 普通节点匹配不足：仅匹配 {len(matched_nodes)} 个节点，无法确认视口",
        log_callback,
    )
    executor._log(
        "  · 建议：移动视口让更多节点完整可见，或放大图形/调整缩放等级",
        log_callback,
    )
    return None


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

    score_value = float(matched_detections) - float(missing_expected_nodes) * float(ORIGIN_VOTING_MISSING_PENALTY)
    return {
        "matched": int(matched_detections),
        "total_detections": int(total_detections),
        "missing": int(missing_expected_nodes),
        "score": score_value,
    }


def recognize_visible_nodes(executor, graph_model: GraphModel) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    log = getattr(executor, "_log", None)
    total_node_count = int(len(getattr(graph_model, "nodes", {}) or {}))
    if callable(log):
        log(f"[可见节点] 开始统计可见节点：模型节点={total_node_count}")

    screenshot: Image.Image | None = None
    detected_nodes: list | None = None

    # 1) 优先尝试场景级快照（视口未变化时跨步骤复用同一帧识别结果）
    used_scene_snapshot: bool = False
    scene_snapshot = None
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
                used_scene_snapshot = True
                if callable(log):
                    log(
                        f"[可见节点] 复用场景快照：检测节点={int(len(detected_nodes))}"
                    )

    # 2) 次优：复用上一次识别缓存（视口拟合阶段产生的一次性结果）
    if screenshot is None or detected_nodes is None:
        cached_screenshot = getattr(executor, "_last_recognition_screenshot", None)
        cached_detected = getattr(executor, "_last_recognition_detected", None)
        if cached_screenshot is not None and cached_detected is not None:
            screenshot = cached_screenshot
            detected_nodes = cached_detected
            if callable(log):
                log(
                    f"[可见节点] 复用上一次识别缓存：检测节点={int(len(detected_nodes))}"
                )
            # 使用后立即清除缓存，确保缓存只在同一操作内有效
            if hasattr(executor, "__dict__"):
                setattr(executor, "_last_recognition_screenshot", None)
                setattr(executor, "_last_recognition_detected", None)

    # 3) 兜底：重新截图并识别节点
    if screenshot is None or detected_nodes is None:
        screenshot = editor_capture.capture_window(executor.window_title)
        if not screenshot:
            if callable(log):
                log("[可见节点] 截图失败，全部节点标记为不可见")
            for node_id in graph_model.nodes.keys():
                result[node_id] = {
                    "visible": False,
                    "bbox": None,
                    "center": None,
                    "screen_center": None,
                }
            return result
        detected_nodes = list_nodes(screenshot)
        if callable(log):
            log(f"[可见节点] 新截图识别：检测节点={int(len(detected_nodes))}")

    # 将本次使用到的 screenshot + detections 回写到场景快照（若尚未由场景快照提供）
    if (not used_scene_snapshot) and (scene_snapshot is not None):
        update_method = getattr(scene_snapshot, "update_from_detection", None)
        if callable(update_method):
            update_method(screenshot, detected_nodes)

    if not detected_nodes:
        if callable(log):
            log("[可见节点] list_nodes 返回空，全部节点标记为不可见")
        for node_id in graph_model.nodes.keys():
            result[node_id] = {
                "visible": False,
                "bbox": None,
                "center": None,
                "screen_center": None,
            }
        return result

    # 预构建 bbox → 检测下标 映射，便于后续通过 bbox 反查唯一检测
    bbox_to_indices: Dict[tuple[int, int, int, int], list[int]] = {}
    # 使用 id(detection) 作为键，避免 NodeDetected 实例不可哈希的问题
    detection_index_by_id: Dict[int, int] = {}
    for det_index, detection in enumerate(detected_nodes):
        bbox_x, bbox_y, bbox_w, bbox_h = detection.bbox
        key = (int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h))
        bbox_to_indices.setdefault(key, []).append(int(det_index))
        detection_index_by_id[id(detection)] = int(det_index)

    # 按中文标题分桶候选检测，沿用原有的“标题优先”策略
    title_to_detections: Dict[str, list] = {}
    for detection in detected_nodes:
        det_title = executor._extract_chinese(getattr(detection, "name_cn", "") or "")
        if not det_title:
            continue
        title_to_detections.setdefault(det_title, []).append(detection)

    # 第一步：为每个节点各自选出“最佳 bbox + 代价”，记录候选对 (node_id, det_index, dist2)
    node_candidates: Dict[str, Dict[str, Any]] = {}
    skipped_no_bbox = 0
    skipped_no_det_index = 0
    skipped_fallback_too_far = 0
    for node_id, node in graph_model.nodes.items():
        title_cn = executor._extract_chinese(node.title)
        program_pos = (float(node.pos[0]), float(node.pos[1]))
        detection_pool = title_to_detections.get(title_cn) if title_cn else None
        candidates = detection_pool if detection_pool else detected_nodes

        debug_info: Dict[str, Any] = {}
        bx, by, bw, bh = _find_best_node_bbox(
            executor,
            screenshot,
            title_cn,
            program_pos,
            debug=debug_info,
            detected_nodes=candidates,
        )
        if int(bw) <= 0 or int(bh) <= 0:
            skipped_no_bbox += 1
            if callable(log) and skipped_no_bbox <= 5:
                failed_reason = str(debug_info.get("failed_reason", "unknown"))
                log(
                    f"[可见节点] 跳过 '{str(getattr(node, 'title', '')).strip()}'(id={node_id})："
                    f"未找到有效bbox（原因={failed_reason}）"
                )
            continue

        bbox_key = (int(bx), int(by), int(bw), int(bh))
        det_indices = bbox_to_indices.get(bbox_key)
        if not det_indices:
            skipped_no_det_index += 1
            if callable(log) and skipped_no_det_index <= 5:
                log(
                    f"[可见节点] 跳过 '{str(getattr(node, 'title', '')).strip()}'(id={node_id})："
                    "bbox 未在检测集中找到匹配索引"
                )
            continue

        det_index = det_indices[0]
        expected_editor_x, expected_editor_y = executor.convert_program_to_editor_coords(
            program_pos[0],
            program_pos[1],
        )
        delta_x = float(bx) - float(expected_editor_x)
        delta_y = float(by) - float(expected_editor_y)
        distance_sq = delta_x * delta_x + delta_y * delta_y

        # 仅对“回退匹配（fallback_used=True）”启用距离过滤：
        # 正常在 ROI 范围内找到的匹配不过滤；
        # 对于跨视口的全局回退结果，当偏移远大于当前位置容差时直接丢弃该候选，
        # 避免将明显不在同一局部结构内的远端节点强行绑定到当前检测框上。
        fallback_used = bool(debug_info.get("fallback_used"))
        if fallback_used:
            scale_value = float(executor.scale_ratio or 1.0)
            pos_threshold_x, pos_threshold_y = compute_position_thresholds(scale_value)
            max_allowed_dist2 = float(pos_threshold_x * pos_threshold_x + pos_threshold_y * pos_threshold_y)
            if distance_sq > max_allowed_dist2:
                skipped_fallback_too_far += 1
                if callable(log) and skipped_fallback_too_far <= 5:
                    log(
                        f"[可见节点] 跳过 '{str(getattr(node, 'title', '')).strip()}'(id={node_id})："
                        f"fallback 匹配距离过大，dist2={distance_sq:.1f} 阈值={max_allowed_dist2:.1f}"
                    )
                continue

        node_candidates[node_id] = {
            "det_index": det_index,
            "bbox": bbox_key,
            "distance_sq": distance_sq,
        }

    # 针对同名多实例节点，按预期坐标与检测框的相对顺序做一次局部重排，
    # 减少“相邻同名节点被错误对调”的情况。
    for title, detections_with_title in title_to_detections.items():
        if len(detections_with_title) < 2:
            continue
        # 收集当前图中具有相同中文标题且已有候选的节点
        same_title_nodes: list[tuple[str, object]] = []
        for node_id, node in graph_model.nodes.items():
            if node_id not in node_candidates:
                continue
            node_title_cn = executor._extract_chinese(getattr(node, "title", "") or "")
            if node_title_cn == title:
                same_title_nodes.append((node_id, node))
        if len(same_title_nodes) < 2:
            continue

        # 仅当第一阶段中“同一检测框被多个节点竞争使用”时才启用重排逻辑；
        # 若每个节点已经拥有唯一的检测索引，则保留第一阶段的结果避免无谓洗牌。
        det_to_nodes_local: Dict[int, list[str]] = {}
        for node_id, _node in same_title_nodes:
            candidate = node_candidates.get(node_id)
            if not candidate:
                continue
            det_index_value = candidate.get("det_index")
            if det_index_value is None:
                continue
            det_index_int = int(det_index_value)
            if det_index_int < 0:
                continue
            det_to_nodes_local.setdefault(det_index_int, []).append(node_id)
        conflict_exists = False
        for _det_index, node_list in det_to_nodes_local.items():
            if len(node_list) > 1:
                conflict_exists = True
                break
        if not conflict_exists:
            # 当前同名多实例在第一阶段已形成一一对应的检测分配，无需重排。
            continue

        # 计算这些节点在编辑器坐标中的预期位置
        expected_positions: list[tuple[str, float, float]] = []
        for node_id, node in same_title_nodes:
            prog_x = float(node.pos[0])
            prog_y = float(node.pos[1])
            editor_x, editor_y = executor.convert_program_to_editor_coords(prog_x, prog_y)
            expected_positions.append((node_id, float(editor_x), float(editor_y)))

        if not expected_positions:
            continue

        xs = [pos[1] for pos in expected_positions]
        ys = [pos[2] for pos in expected_positions]
        spread_x = max(xs) - min(xs)
        spread_y = max(ys) - min(ys)
        use_x_axis = bool(spread_x >= spread_y)

        # 收集该标题下所有检测框及其索引
        detection_entries: list[tuple[int, float, float]] = []
        for det in detections_with_title:
            det_index = detection_index_by_id.get(id(det))
            if det_index is None:
                continue
            bbox_x, bbox_y, _w, _h = det.bbox
            detection_entries.append((int(det_index), float(bbox_x), float(bbox_y)))

        if len(detection_entries) < 2:
            continue

        if use_x_axis:
            expected_sorted = sorted(expected_positions, key=lambda item: item[1])
            detection_sorted = sorted(detection_entries, key=lambda item: item[1])
        else:
            expected_sorted = sorted(expected_positions, key=lambda item: item[2])
            detection_sorted = sorted(detection_entries, key=lambda item: item[2])

        pair_count = min(len(expected_sorted), len(detection_sorted))
        for index in range(pair_count):
            node_id, exp_x, exp_y = expected_sorted[index]
            det_index, det_x, det_y = detection_sorted[index]
            detection_obj = detected_nodes[det_index]
            bx, by, bw, bh = detection_obj.bbox
            delta_x = float(bx) - float(exp_x)
            delta_y = float(by) - float(exp_y)
            distance_sq = delta_x * delta_x + delta_y * delta_y
            node_candidates[node_id] = {
                "det_index": int(det_index),
                "bbox": (int(bx), int(by), int(bw), int(bh)),
                "distance_sq": distance_sq,
            }

    if callable(log):
        log(
            f"[可见节点] 第一阶段匹配完成：有候选节点={int(len(node_candidates))}，"
            f"无bbox={int(skipped_no_bbox)}，无索引={int(skipped_no_det_index)}，"
            f"fallback超距={int(skipped_fallback_too_far)}"
        )

    # 第二步：以“距离平方最小”作为代价，对每个检测框只保留一个最佳节点，形成全局一对一分配
    det_to_best: Dict[int, tuple[str, float]] = {}
    for node_id, candidate in node_candidates.items():
        det_index = candidate["det_index"]
        dist2 = float(candidate["distance_sq"])
        existing = det_to_best.get(det_index)
        if existing is None or dist2 < existing[1]:
            det_to_best[det_index] = (node_id, dist2)

    assigned_node_to_bbox: Dict[str, tuple[int, int, int, int]] = {}
    for det_index, (best_node_id, _) in det_to_best.items():
        detection = detected_nodes[det_index]
        bx, by, bw, bh = detection.bbox
        assigned_node_to_bbox[best_node_id] = (
            int(bx),
            int(by),
            int(bw),
            int(bh),
        )

    if callable(log):
        log(
            f"[可见节点] 第二阶段分配完成：参与分配的节点数={int(len(assigned_node_to_bbox))}，"
            f"检测节点数={int(len(detected_nodes))}"
        )

    # 第三步：构建最终可见性映射；未参与分配或无检测的节点一律标记为不可见
    visible_ids: list[str] = []
    for node_id in graph_model.nodes.keys():
        bbox = assigned_node_to_bbox.get(node_id)
        if bbox is None:
            result[node_id] = {
                "visible": False,
                "bbox": None,
                "center": None,
                "screen_center": None,
            }
            continue

        bx, by, bw, bh = bbox
        # 对外暴露的节点位置语义仍然采用 bbox 左上角作为锚点；
        # 如需绘制圆形高亮，可在 UI 层自行根据宽高计算几何中心。
        anchor_x = int(bx)
        anchor_y = int(by)
        screen_x, screen_y = executor.convert_editor_to_screen_coords(
            int(anchor_x),
            int(anchor_y),
        )
        result[node_id] = {
            "visible": True,
            "bbox": (int(bx), int(by), int(bw), int(bh)),
            "center": (int(anchor_x), int(anchor_y)),
            "screen_center": (int(screen_x), int(screen_y)),
        }
        visible_ids.append(node_id)

    if callable(log):
        preview_titles: list[str] = []
        for vid in visible_ids[:10]:
            node_model = graph_model.nodes.get(vid)
            if node_model is not None and getattr(node_model, "title", None) is not None:
                preview_titles.append(str(node_model.title).strip())
        log(
            f"[可见节点] 最终可见节点={int(len(visible_ids))}/{total_node_count}"
            + (f"：{preview_titles}" if preview_titles else "")
        )

    return result


def is_node_visible_by_id(executor, graph_model: GraphModel, node_id: str) -> bool:
    if node_id not in graph_model.nodes:
        return False
    mapping = recognize_visible_nodes(executor, graph_model)
    info = mapping.get(node_id)
    return bool(info and info.get("visible"))


def verify_and_update_view_mapping_by_recognition(
    executor,
    graph_model: GraphModel,
    log_callback=None,
    visual_callback=None,
    allow_degraded_fallback: bool = True,
) -> bool:
    """
    通过视觉识别校验并更新视口映射。

    流程概要：
    1. 截图并检测所有节点；
    2. 基于“检测左上角 - 程序坐标”的原点平移样本，在固定缩放比例 1.0 的前提下进行平移投票聚类；
    3. 对若干候选原点进行精细评估（匹配检测数量 + 缺失惩罚），选出得分最高的一项；
    4. 将选出的原点写入执行器，并缓存识别结果供后续复用。
    """
    screenshot = executor.capture_and_emit(
        label="识别-首帧",
        overlays_builder=build_graph_region_overlay,
        visual_callback=visual_callback,
    )
    if not screenshot:
        executor._log("✗ 截图失败（识别校验）", log_callback)
        return False

    invalidate_cache()
    detected = list_nodes(screenshot)
    # 视口拟合阶段的识别结果也回写到场景快照，方便后续步骤在视口未变化时复用
    get_scene_snapshot = getattr(executor, "get_scene_snapshot", None)
    if callable(get_scene_snapshot) and bool(
        getattr(executor, "enable_scene_snapshot_optimization", True)
    ):
        scene_snapshot = get_scene_snapshot()
        update_method = getattr(scene_snapshot, "update_from_detection", None)
        if callable(update_method):
            update_method(screenshot, detected)
    log_detection_snapshot(executor, screenshot, detected, log_callback, visual_callback)

    _dump_last_focus_detection_snapshot(
        executor,
        graph_model,
        detected,
    )

    mappings = build_detection_mappings(executor, graph_model, detected)

    executor._log(
        f"[识别] 模型节点 {len(mappings.unique_model_names)} 个，检测节点 {len(mappings.unique_detected_names)} 个，"
        f"共同标题 {len(mappings.shared_names)} 个",
        log_callback,
    )

    origin_samples = _generate_origin_samples(mappings)
    if not origin_samples:
        executor._log("[平移投票] 无可用原点样本，可能缺少共享标题或检测结果为空", log_callback)
        return False

    executor._log(
        f"[平移投票] 原点样本数={len(origin_samples)}，开始网格聚类",
        log_callback,
    )
    candidate_origins = _cluster_origin_samples(origin_samples)
    if not candidate_origins:
        executor._log("[平移投票] 无法从样本中构造原点候选簇", log_callback)
        return False

    region_x: int
    region_y: int
    region_width: int
    region_height: int
    region_rect: Optional[tuple[int, int, int, int]] = None
    region_x, region_y, region_width, region_height = editor_capture.get_region_rect(
        screenshot,
        "节点图布置区域",
    )
    region_rect = (int(region_x), int(region_y), int(region_width), int(region_height))

    base_tolerance_x, base_tolerance_y = compute_position_thresholds(FIXED_SCALE_RATIO)
    position_tolerance_x = float(base_tolerance_x) * float(ORIGIN_VOTING_POSITION_TOL_MULTIPLIER)
    position_tolerance_y = float(base_tolerance_y) * float(ORIGIN_VOTING_POSITION_TOL_MULTIPLIER)

    best_result: Optional[dict[str, Any]] = None
    best_origin_x: float = 0.0
    best_origin_y: float = 0.0

    for index, (candidate_origin_x, candidate_origin_y, vote_count) in enumerate(candidate_origins, start=1):
        evaluation = _evaluate_origin_candidate(
            executor,
            mappings,
            float(candidate_origin_x),
            float(candidate_origin_y),
            region_rect,
            position_tolerance_x,
            position_tolerance_y,
        )
        matched_count = int(evaluation["matched"])
        missing_count = int(evaluation["missing"])
        score_value = float(evaluation["score"])
        executor._log(
            f"[平移投票] 候选{index}: origin≈({candidate_origin_x:.1f},{candidate_origin_y:.1f}) "
            f"投票={vote_count} 命中={matched_count} 缺失={missing_count} 得分={score_value:.1f}",
            log_callback,
        )
        if best_result is None or score_value > float(best_result["score"]):
            best_result = evaluation
            best_origin_x = float(candidate_origin_x)
            best_origin_y = float(candidate_origin_y)

    if best_result is None or int(best_result["matched"]) < ORIGIN_VOTING_MIN_INLIERS:
        executor._log(
            f"[平移投票] 校准失败：有效原点候选不足（命中样本 {0 if best_result is None else int(best_result['matched'])}）",
            log_callback,
        )
        return False

    executor.scale_ratio = FIXED_SCALE_RATIO
    executor.origin_node_pos = (int(round(best_origin_x)), int(round(best_origin_y)))

    fit_result: ViewMappingFitResult = ViewMappingFitResult(
        success=True,
        strategy=FIT_STRATEGY_ORIGIN_TRANSLATION,
    )
    if hasattr(executor, "__dict__"):
        setattr(executor, "_last_view_mapping_strategy", fit_result.strategy)
        setattr(executor, "_last_recognition_screenshot", screenshot)
        setattr(executor, "_last_recognition_detected", detected)
    
    executor._log(
        f"✓ 视口映射成功：策略={fit_result.strategy} scale={executor.scale_ratio:.4f} "
        f"origin=({executor.origin_node_pos[0]},{executor.origin_node_pos[1]})",
        log_callback,
    )
    return True


def synchronize_visible_nodes_positions(
    executor,
    graph_model: GraphModel,
    threshold_px: float = 40.0,
    log_callback=None,
) -> int:
    """
    根据当前识别结果估算可见节点的程序坐标偏移，避免视口偏移后仍使用过期位置。

    Args:
        executor: 执行器实例
        graph_model: 图模型
        threshold_px: 仅当左上角偏移超过该阈值（像素）才更新

    Returns:
        int: 实际被更新的节点数量
    """
    if executor.scale_ratio is None or executor.origin_node_pos is None:
        return 0

    scale = float(executor.scale_ratio)
    if abs(scale) <= 1e-6:
        return 0

    origin_x = float(executor.origin_node_pos[0])
    origin_y = float(executor.origin_node_pos[1])
    visible_map = recognize_visible_nodes(executor, graph_model)
    if not visible_map:
        if hasattr(executor, "__dict__"):
            executor._recent_node_position_deltas = {}
            executor._position_delta_token = getattr(executor, "_view_state_token", 0)
        return 0

    # 步骤感知重映射：当同名节点存在多个实例且包含“未来步骤节点”时，
    # 优先将检测结果绑定到“已到达当前步骤”的实例，避免偏移被未来步骤抢占。
    node_first_index_map = getattr(executor, "_node_first_create_step_index", None)
    current_step_index = getattr(executor, "_current_step_index", None)
    if isinstance(node_first_index_map, dict) and isinstance(current_step_index, int):
        title_groups: Dict[str, list[tuple[str, Optional[int], bool, Optional[tuple[int, int, int, int]]]]] = {}
        for node_id, node in graph_model.nodes.items():
            info = visible_map.get(node_id)
            is_visible = bool(info and info.get("visible"))
            bbox = info.get("bbox") if info else None
            first_index = node_first_index_map.get(node_id)
            title = getattr(node, "title", "")
            title_groups.setdefault(title, []).append((node_id, first_index, is_visible, bbox))

        for _title, group in title_groups.items():
            if len(group) <= 1:
                continue
            visible_entries = [entry for entry in group if entry[2] and entry[3] is not None]
            if not visible_entries:
                continue
            eligible_entries = [
                entry
                for entry in group
                if (entry[1] is None) or (entry[1] <= current_step_index)
            ]
            if not eligible_entries:
                continue

            def _step_distance(entry: tuple[str, Optional[int], bool, Optional[tuple[int, int, int, int]]]) -> int:
                first_idx = entry[1]
                if first_idx is None:
                    return 10**9
                return abs(int(first_idx) - int(current_step_index))

            eligible_sorted = sorted(eligible_entries, key=_step_distance)
            bboxes = [entry[3] for entry in visible_entries]

            # 先清空该标题下所有节点的可见标记与 bbox
            for node_id, _first_idx, _is_visible, _bbox in group:
                info = visible_map.get(node_id)
                if info is not None:
                    info["visible"] = False
                    info["bbox"] = None

            # 再依次将现有 bbox 分配给“离当前步骤最近的已创建实例”
            for index, bbox in enumerate(bboxes):
                if bbox is None or index >= len(eligible_sorted):
                    break
                target_id = eligible_sorted[index][0]
                info = visible_map.get(target_id)
                if info is None:
                    continue
                info["visible"] = True
                info["bbox"] = bbox

    position_deltas: Dict[str, Tuple[float, float]] = {}
    if hasattr(executor, "__dict__"):
        executor._recent_node_position_deltas = position_deltas
    else:
        position_deltas = {}

    auto_threshold_x, _ = compute_position_thresholds(scale)
    adjust_threshold = float(max(threshold_px, auto_threshold_x * 0.5))

    updated = 0
    for node_id, info in visible_map.items():
        if not info.get('visible'):
            continue
        node = graph_model.nodes.get(node_id)
        if node is None:
            continue
        bbox = info.get('bbox')
        if not bbox:
            continue
        left_v, top_v, _, _ = bbox
        expected_x, expected_y = executor.convert_program_to_editor_coords(
            float(node.pos[0]),
            float(node.pos[1]),
        )
        dx = abs(float(left_v) - float(expected_x))
        dy = abs(float(top_v) - float(expected_y))
        if dx <= adjust_threshold and dy <= adjust_threshold:
            continue
        old_prog_x, old_prog_y = float(node.pos[0]), float(node.pos[1])
        new_prog_x = (float(left_v) - origin_x) / scale
        new_prog_y = (float(top_v) - origin_y) / scale
        delta_x = new_prog_x - old_prog_x
        delta_y = new_prog_y - old_prog_y
        updated += 1
        executor._log(
            f"[识别同步] '{node.title}' 偏移≈({dx:.1f},{dy:.1f}) → 记录程序坐标偏移 Δ≈({delta_x:.1f},{delta_y:.1f})",
            log_callback,
        )
        if position_deltas is not None:
            position_deltas[node_id] = (delta_x, delta_y)

    if hasattr(executor, "__dict__"):
        executor._position_delta_token = getattr(executor, "_view_state_token", 0)

    return updated


def _find_best_node_bbox(
    executor,
    screenshot: Image.Image,
    title_cn: str,
    program_pos: tuple[float, float],
    debug: Optional[Dict[str, Any]] = None,
    detected_nodes: Optional[list] = None,
) -> tuple[int, int, int, int]:
    from app.automation.vision.node_detection import find_best_node_bbox as _find_best_node_bbox_ext

    return _find_best_node_bbox_ext(executor, screenshot, title_cn, program_pos, debug, detected_nodes)


def _update_position_delta_cache_from_matches(
    executor,
    matches: list[dict[str, Any]],
    scale_x: float,
    scale_y: float,
    offset_x: float,
    offset_y: float,
) -> None:
    if not hasattr(executor, "__dict__"):
        return
    if not matches:
        return
    safe_sx = scale_x if abs(scale_x) > 1e-6 else 1.0
    safe_sy = scale_y if abs(scale_y) > 1e-6 else 1.0
    deltas: Dict[str, Tuple[float, float]] = {}
    for record in matches:
        node = record.get("node")
        det_center = record.get("detection_center")
        expected_center = record.get("expected_center")
        if node is None or det_center is None or expected_center is None:
            continue
        node_id = getattr(node, "id", "")
        if not node_id:
            continue
        editor_dx = float(det_center[0]) - float(expected_center[0])
        editor_dy = float(det_center[1]) - float(expected_center[1])
        prog_dx = editor_dx / safe_sx
        prog_dy = editor_dy / safe_sy
        if abs(prog_dx) < 1e-3 and abs(prog_dy) < 1e-3:
            continue
        deltas[node_id] = (prog_dx, prog_dy)
    if not deltas:
        return
    existing = getattr(executor, "_recent_node_position_deltas", None)
    if isinstance(existing, dict):
        existing.update(deltas)
        executor._recent_node_position_deltas = existing
    else:
        executor._recent_node_position_deltas = deltas
    executor._position_delta_token = getattr(executor, "_view_state_token", 0)

