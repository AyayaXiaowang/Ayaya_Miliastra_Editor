# -*- coding: utf-8 -*-
"""
editor_recognition.view_mapping_relative_anchors

相对锚点邻域匹配：
- 不依赖先验校准：通过锚点与邻居的相对几何比例匹配检测框与模型节点
- 命中足够邻居后，再对所有共享标题做支持度评估，确认映射稳定性
"""

from __future__ import annotations

from statistics import median
import math
from typing import Any, Dict, Optional, Tuple

from app.automation.input.common import compute_position_thresholds
from app.automation.editor.editor_mapping import FIXED_SCALE_RATIO

from .constants import (
    FIT_STRATEGY_RELATIVE_ANCHORS,
    RELATIVE_ANCHOR_MAX_ANISOTROPY,
    RELATIVE_ANCHOR_MAX_NEIGHBORS,
    RELATIVE_ANCHOR_MIN_MATCHES,
    RELATIVE_ANCHOR_MIN_PROG_DELTA,
    RELATIVE_ANCHOR_TOLERANCE_MULTIPLIER,
    UNIQUE_RATIO_TOLERANCE,
)
from .models import MappingData, ViewMappingFitResult
from .view_mapping_geometry_helpers import (
    _build_detection_centers_by_title,
    _compute_global_centers,
    _flatten_model_nodes,
)


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
        executor.log("[相对匹配] 当前画面无可用检测节点", log_callback)
        return None
    all_model_nodes = _flatten_model_nodes(mappings)
    if not all_model_nodes:
        executor.log("[相对匹配] 模型节点为空", log_callback)
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
            executor.log("[相对匹配] 未找到唯一标题锚点，转为普通节点", log_callback)
        else:
            executor.log("[相对匹配] 无可用锚点候选", log_callback)
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
        executor.log(
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
    executor.log(
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
            executor.log(
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
        setattr(executor, "_recent_node_position_deltas", existing)
    else:
        setattr(executor, "_recent_node_position_deltas", deltas)
    setattr(executor, "_position_delta_token", getattr(executor, "_view_state_token", 0))


