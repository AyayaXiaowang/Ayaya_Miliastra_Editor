# -*- coding: utf-8 -*-
"""
editor_recognition.fallbacks

降级策略与锚点/唯一标题辅助逻辑。
"""

from __future__ import annotations

import math
from statistics import median
from typing import Callable, Optional

from PIL import Image

from app.automation.core.editor_mapping import MIN_SCALE_RATIO, FIXED_SCALE_RATIO
from engine.graph.models.graph_model import NodeModel

from .constants import (
    ANCHOR_PAIR_MAX_SCALE,
    ANCHOR_PAIR_MIN_MATCHES,
    ANCHOR_PAIR_MIN_RATIO,
    SINGLE_ANCHOR_MIN_MATCHES,
    SINGLE_ANCHOR_MIN_RATIO,
    UNIQUE_RATIO_MAX_RESIDUAL_PX,
    UNIQUE_RATIO_MIN_REFERENCES,
    UNIQUE_RATIO_TOLERANCE,
)
from .models import MappingData


def collect_unique_titles(shared_names, name_to_model_nodes, name_to_detections):
    return [
        nm
        for nm in shared_names
        if len(name_to_model_nodes.get(nm, [])) == 1 and len(name_to_detections.get(nm, [])) == 1
    ]


def _collect_unique_alignment_points(unique_titles, mappings: MappingData):
    points: list[dict] = []
    for name in unique_titles:
        model_list = mappings.name_to_model_nodes.get(name, [])
        detections = mappings.name_to_detections.get(name, [])
        if not model_list or not detections:
            continue
        model_node = model_list[0]
        det_bbox = detections[0]
        prog_x = float(model_node.pos[0])
        prog_y = float(model_node.pos[1])
        det_x = float(det_bbox[0]) + float(det_bbox[2]) * 0.5
        det_y = float(det_bbox[1]) + float(det_bbox[3]) * 0.5
        points.append(
            {
                "title": name,
                "prog": (prog_x, prog_y),
                "det": (det_x, det_y),
                "bbox": det_bbox,
            }
        )
    return points


def _compute_axis_scale(points: list[dict], axis: int, tolerance: float) -> Optional[float]:
    ratios: list[float] = []
    for idx in range(len(points)):
        for jdx in range(idx + 1, len(points)):
            prog_delta = abs(points[jdx]["prog"][axis] - points[idx]["prog"][axis])
            det_delta = abs(points[jdx]["det"][axis] - points[idx]["det"][axis])
            if prog_delta < 1.0 or det_delta < 1.0:
                continue
            ratios.append(det_delta / prog_delta)
    if not ratios:
        return None
    median_ratio = median(ratios)
    if float(abs(median_ratio)) <= 1e-6:
        return None
    allowed = 0
    for ratio in ratios:
        max_ref = max(abs(median_ratio), 0.01)
        if abs(ratio - median_ratio) <= tolerance * max_ref:
            allowed += 1
    if allowed < max(1, int(len(ratios) * 0.5)):
        return None
    return float(median_ratio)


def _compute_axis_translation(points: list[dict], axis: int, scale_val: float) -> Optional[float]:
    offsets = [point["det"][axis] - scale_val * point["prog"][axis] for point in points]
    if not offsets:
        return None
    return float(median(offsets))


def _validate_unique_alignment(
    points: list[dict],
    scale_x: float,
    scale_y: float,
    tx: float,
    ty: float,
    residual_limit: float,
) -> bool:
    for point in points:
        pred_x = scale_x * point["prog"][0] + tx
        pred_y = scale_y * point["prog"][1] + ty
        err_x = abs(pred_x - point["det"][0])
        err_y = abs(pred_y - point["det"][1])
        if err_x > residual_limit or err_y > residual_limit:
            return False
    return True


def try_unique_ratio_alignment(
    executor,
    screenshot: Image.Image,
    unique_titles,
    mappings: MappingData,
    log_callback,
    visual_callback,
    ratio_tolerance: float = UNIQUE_RATIO_TOLERANCE,
) -> bool:
    if len(unique_titles) < UNIQUE_RATIO_MIN_REFERENCES:
        executor.log(
            f"[唯一比例] 候选不足：{len(unique_titles)} < {UNIQUE_RATIO_MIN_REFERENCES}",
            log_callback,
        )
        return False
    points = _collect_unique_alignment_points(unique_titles, mappings)
    if len(points) < UNIQUE_RATIO_MIN_REFERENCES:
        executor.log(
            f"[唯一比例] 可用节点不足：{len(points)} < {UNIQUE_RATIO_MIN_REFERENCES}",
            log_callback,
        )
        return False
    scale_x = _compute_axis_scale(points, axis=0, tolerance=float(ratio_tolerance))
    scale_y = _compute_axis_scale(points, axis=1, tolerance=float(ratio_tolerance))
    if scale_x is None and scale_y is None:
        executor.log("[唯一比例] 计算失败：X/Y 均无有效比例", log_callback)
        return False
    if scale_x is None:
        scale_x = scale_y if scale_y is not None else 1.0
    if scale_y is None:
        scale_y = scale_x if scale_x is not None else 1.0
    tx = _compute_axis_translation(points, axis=0, scale_val=float(scale_x))
    ty = _compute_axis_translation(points, axis=1, scale_val=float(scale_y))
    if tx is None or ty is None:
        executor.log("[唯一比例] 平移估算失败：无可用参考", log_callback)
        return False
    if not _validate_unique_alignment(
        points,
        float(scale_x),
        float(scale_y),
        float(tx),
        float(ty),
        float(UNIQUE_RATIO_MAX_RESIDUAL_PX),
    ):
        executor.log("[唯一比例] 验证失败：残差超限", log_callback)
        return False
    measured_avg = float((float(scale_x) + float(scale_y)) * 0.5)
    executor.scale_ratio = FIXED_SCALE_RATIO
    executor.origin_node_pos = (int(round(tx)), int(round(ty)))
    executor.log(
        f"[唯一比例] 对齐成功：参与 {len(points)} 个，ratio_x={float(scale_x):.4f} ratio_y={float(scale_y):.4f} "
        f"avg≈{measured_avg:.4f}→固定 {executor.scale_ratio:.2f}",
        log_callback,
    )
    if visual_callback is not None:
        rects = [
            {
                "bbox": (
                    int(point["bbox"][0]),
                    int(point["bbox"][1]),
                    int(point["bbox"][2]),
                    int(point["bbox"][3]),
                ),
                "color": (0, 200, 255),
                "label": f"唯一·{point['title']}",
            }
            for point in points
        ]
        executor.emit_visual(screenshot, {"rects": rects}, visual_callback)
    return True


def iter_unique_anchor_candidates(mappings: MappingData):
    for name in mappings.shared_names:
        models = mappings.name_to_model_nodes.get(name, [])
        detections = mappings.name_to_detections.get(name, [])
        if len(detections) == 1 and len(models) >= 1:
            yield name, models[0], detections


def _detection_matches_any_model(
    models: list[NodeModel],
    win_x: float,
    win_y: float,
    scale_val: float,
    tx: float,
    ty: float,
    epsilon_px: float,
) -> bool:
    for model in models:
        prog_x = float(model.pos[0])
        prog_y = float(model.pos[1])
        pred_x = scale_val * prog_x + tx
        pred_y = scale_val * prog_y + ty
        if math.hypot(pred_x - win_x, pred_y - win_y) <= float(epsilon_px):
            return True
    return False


def evaluate_anchor_transform_support(
    mappings: MappingData,
    scale_val: float,
    tx: float,
    ty: float,
    epsilon_px: float,
) -> Optional[dict]:
    total = 0
    matched = 0
    matched_names: list[str] = []
    for name in mappings.shared_names:
        detections = mappings.name_to_detections.get(name, [])
        models = mappings.name_to_model_nodes.get(name, [])
        if not detections or not models:
            continue
        total += len(detections)
        for detection in detections:
            win_x = float(detection[0])
            win_y = float(detection[1])
            if _detection_matches_any_model(models, win_x, win_y, scale_val, tx, ty, epsilon_px):
                matched += 1
                matched_names.append(name)
                break
    if total <= 0:
        return None
    ratio = float(matched) / float(total)
    return {
        "matched_count": matched,
        "total_count": total,
        "ratio": ratio,
        "matched_names": matched_names,
    }


def try_unique_anchor_pair_transform(
    executor,
    screenshot: Image.Image,
    mappings: MappingData,
    epsilon_px: float,
    log_callback,
    visual_callback,
) -> bool:
    anchors = list(iter_unique_anchor_candidates(mappings))
    if len(anchors) < 2:
        executor.log("[锚点] 未采用：唯一标题不足2个", log_callback)
        return False

    detection_total = sum(len(mappings.name_to_detections.get(name, [])) for name in mappings.shared_names)
    min_required_matches = max(2, min(ANCHOR_PAIR_MIN_MATCHES, detection_total))
    executor.log(
        f"[锚点] 尝试唯一锚点对齐：anchors={len(anchors)} 目标命中≥{min_required_matches} 比例≥{ANCHOR_PAIR_MIN_RATIO:.2f}",
        log_callback,
    )

    best_choice: Optional[dict] = None
    best_eval_ratio: float = 0.0
    best_eval_matches: int = 0

    for idx_a in range(len(anchors)):
        name_a, model_a, detections_a = anchors[idx_a]
        prog_a = (float(model_a.pos[0]), float(model_a.pos[1]))
        for idx_b in range(idx_a + 1, len(anchors)):
            name_b, model_b, detections_b = anchors[idx_b]
            prog_b = (float(model_b.pos[0]), float(model_b.pos[1]))
            prog_dist = math.hypot(prog_b[0] - prog_a[0], prog_b[1] - prog_a[1])
            if prog_dist <= 1.0:
                continue
            for det_a in detections_a:
                win_a = (float(det_a[0]), float(det_a[1]))
                for det_b in detections_b:
                    win_b = (float(det_b[0]), float(det_b[1]))
                    win_dist = math.hypot(win_b[0] - win_a[0], win_b[1] - win_a[1])
                    if win_dist <= 1.0:
                        continue
                    scale_val = win_dist / prog_dist
                    if scale_val <= MIN_SCALE_RATIO or scale_val > ANCHOR_PAIR_MAX_SCALE:
                        continue
                    tx = win_a[0] - scale_val * prog_a[0]
                    ty = win_a[1] - scale_val * prog_a[1]
                    support = evaluate_anchor_transform_support(mappings, scale_val, tx, ty, epsilon_px)
                    if support is None:
                        continue
                    if float(support["ratio"]) > float(best_eval_ratio) or int(support["matched_count"]) > int(best_eval_matches):
                        best_eval_ratio = float(support["ratio"])
                        best_eval_matches = int(support["matched_count"])
                    if support["matched_count"] < min_required_matches:
                        continue
                    if support["ratio"] < ANCHOR_PAIR_MIN_RATIO:
                        continue
                    if (
                        best_choice is None
                        or support["matched_count"] > best_choice["support"]["matched_count"]
                        or (
                            support["matched_count"] == best_choice["support"]["matched_count"]
                            and support["ratio"] > best_choice["support"]["ratio"]
                        )
                    ):
                        best_choice = {
                            "scale": scale_val,
                            "tx": tx,
                            "ty": ty,
                            "support": support,
                            "anchors": ((name_a, det_a), (name_b, det_b)),
                        }

    if best_choice is None:
        executor.log(
            f"[锚点] 未采用：anchors={len(anchors)} 支持={best_eval_matches}/{detection_total} ({best_eval_ratio:.2f}) "
            f"阈值: 匹配≥{min_required_matches}, 比例≥{ANCHOR_PAIR_MIN_RATIO:.2f}",
            log_callback,
        )
        return False

    measured_scale = float(best_choice["scale"])
    executor.scale_ratio = FIXED_SCALE_RATIO
    executor.origin_node_pos = (
        int(round(best_choice["tx"])),
        int(round(best_choice["ty"])),
    )
    matched_cnt = best_choice["support"]["matched_count"]
    total_cnt = best_choice["support"]["total_count"]
    ratio = best_choice["support"]["ratio"]
    anchor_names = ", ".join(name for name, _ in best_choice["anchors"])
    executor.log(
        f"⚠ 唯一锚点降级：使用 {anchor_names} 对齐 scale_est≈{measured_scale:.4f}→固定 {executor.scale_ratio:.2f} "
        f"命中={matched_cnt}/{total_cnt} ({ratio:.2f})",
        log_callback,
    )
    if visual_callback is not None:
        rects = []
        for anchor_name, det_bbox in best_choice["anchors"]:
            rects.append(
                {
                    "bbox": (int(det_bbox[0]), int(det_bbox[1]), int(det_bbox[2]), int(det_bbox[3])),
                    "color": (255, 140, 60),
                    "label": f"锚点·{anchor_name}",
                }
            )
        executor.emit_visual(screenshot, {"rects": rects}, visual_callback)
    return True


def try_single_anchor_scale_transform(
    executor,
    screenshot: Image.Image,
    mappings: MappingData,
    epsilon_px: float,
    log_callback,
    visual_callback,
) -> bool:
    anchors = list(iter_unique_anchor_candidates(mappings))
    if len(anchors) < 1:
        executor.log("[单锚] 未采用：唯一标题不足1个", log_callback)
        return False

    detection_total = sum(len(mappings.name_to_detections.get(name, [])) for name in mappings.shared_names)
    min_required_matches = max(2, min(SINGLE_ANCHOR_MIN_MATCHES, detection_total))
    executor.log(
        f"[单锚] 尝试单一锚点估算：anchors={len(anchors)} 目标命中≥{min_required_matches} 比例≥{SINGLE_ANCHOR_MIN_RATIO:.2f}",
        log_callback,
    )

    import numpy as _np

    best_choice: Optional[dict] = None
    best_eval_ratio: float = 0.0
    best_eval_matches: int = 0

    for name_a, model_a, detections_a in anchors:
        prog_a = (float(model_a.pos[0]), float(model_a.pos[1]))
        for detection in detections_a:
            win_a = (float(detection[0]), float(detection[1]))
            scale_samples: list[float] = []
            for shared_name in mappings.shared_names:
                if shared_name == name_a:
                    continue
                models_b = mappings.name_to_model_nodes.get(shared_name, [])
                detections_b = mappings.name_to_detections.get(shared_name, [])
                if not models_b or not detections_b:
                    continue
                for det_b in detections_b:
                    win_b = (float(det_b[0]), float(det_b[1]))
                    dist_win = math.hypot(win_b[0] - win_a[0], win_b[1] - win_a[1])
                    if dist_win <= 1.0:
                        continue
                    for model_b in models_b:
                        prog_b = (float(model_b.pos[0]), float(model_b.pos[1]))
                        dist_prog = math.hypot(prog_b[0] - prog_a[0], prog_b[1] - prog_a[1])
                        if dist_prog <= 1.0:
                            continue
                        scale_samples.append(float(dist_win) / float(dist_prog))
            if len(scale_samples) == 0:
                continue
            scale_est = float(_np.median(_np.array(scale_samples, dtype=_np.float64)))
            if scale_est <= float(MIN_SCALE_RATIO) or scale_est > float(ANCHOR_PAIR_MAX_SCALE):
                continue
            tx = win_a[0] - scale_est * prog_a[0]
            ty = win_a[1] - scale_est * prog_a[1]
            support = evaluate_anchor_transform_support(mappings, scale_est, tx, ty, epsilon_px)
            if support is None:
                continue
            best_eval_ratio = max(best_eval_ratio, float(support["ratio"]))
            best_eval_matches = max(best_eval_matches, int(support["matched_count"]))
            if support["matched_count"] < min_required_matches or support["ratio"] < float(SINGLE_ANCHOR_MIN_RATIO):
                continue
            if (
                best_choice is None
                or support["matched_count"] > best_choice["support"]["matched_count"]
                or (
                    support["matched_count"] == best_choice["support"]["matched_count"]
                    and support["ratio"] > best_choice["support"]["ratio"]
                )
            ):
                best_choice = {
                    "scale": scale_est,
                    "tx": tx,
                    "ty": ty,
                    "support": support,
                    "anchor": (name_a, detection),
                }

    if best_choice is None:
        executor.log(
            f"[单锚] 未采用：支持={best_eval_matches}/{detection_total} ({best_eval_ratio:.2f}) "
            f"阈值: 匹配≥{min_required_matches}, 比例≥{float(SINGLE_ANCHOR_MIN_RATIO):.2f}",
            log_callback,
        )
        return False

    measured_scale = float(best_choice["scale"])
    executor.scale_ratio = FIXED_SCALE_RATIO
    executor.origin_node_pos = (int(round(best_choice["tx"])), int(round(best_choice["ty"])))
    matched_cnt = best_choice["support"]["matched_count"]
    total_cnt = best_choice["support"]["total_count"]
    ratio = best_choice["support"]["ratio"]
    anchor_name = best_choice["anchor"][0]
    executor.log(
        f"⚠ 单锚估算：使用 {anchor_name} 对齐 scale_est≈{measured_scale:.4f}→固定 {executor.scale_ratio:.2f} "
        f"命中={matched_cnt}/{total_cnt} ({ratio:.2f})",
        log_callback,
    )
    if visual_callback is not None:
        det_bbox = best_choice["anchor"][1]
        rects = [
            {
                "bbox": (int(det_bbox[0]), int(det_bbox[1]), int(det_bbox[2]), int(det_bbox[3])),
                "color": (255, 180, 60),
                "label": f"单锚·{anchor_name}",
            }
        ]
        executor.emit_visual(screenshot, {"rects": rects}, visual_callback)
    return True

