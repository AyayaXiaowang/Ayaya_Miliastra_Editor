# -*- coding: utf-8 -*-
"""
editor_recognition.view_mapping

视口映射高层入口：截图 → 节点检测 → 映射拟合 → 写入 executor.scale_ratio / origin_node_pos。
具体算法拆分在 `view_mapping_origin_voting` / `view_mapping_relative_anchors` / `view_mapping_single_anchor` 等模块。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.automation import capture as editor_capture
from app.automation.input.common import build_graph_region_overlay, compute_position_thresholds
from app.automation.vision import invalidate_cache, list_nodes
from app.automation.editor.editor_mapping import FIXED_SCALE_RATIO
from engine.graph.models.graph_model import GraphModel

from .constants import FIT_STRATEGY_ORIGIN_TRANSLATION, FIT_STRATEGY_UNIQUE_RATIO_ALIGNMENT
from .debug_dump import _dump_last_focus_detection_snapshot
from .fallbacks import collect_unique_titles, try_unique_ratio_alignment
from .logging_utils import log_detection_snapshot
from .mappings import build_detection_mappings
from .models import ViewMappingFitResult
from .view_mapping_ordinary_nodes import _try_ordinary_nodes_position_match
from .view_mapping_origin_voting import (
    ORIGIN_VOTING_MIN_INLIERS,
    ORIGIN_VOTING_POSITION_TOL_MULTIPLIER,
    _cluster_origin_samples,
    _evaluate_origin_candidate,
    _generate_origin_samples,
)
from .view_mapping_relative_anchors import _try_relative_anchor_alignment
from .view_mapping_single_anchor import _try_single_anchor_mapping


@dataclass(frozen=True)
class _ViewMappingStrategySpec:
    name: str
    allow_when_degraded: bool
    requires_post_validation: bool
    runner: Callable[
        [
            object,
            object,
            object,
            object,
            object,
        ],
        Optional[ViewMappingFitResult],
    ]


def _cache_last_recognition_state(executor, screenshot, detected, strategy: str) -> None:
    if hasattr(executor, "__dict__"):
        setattr(executor, "_last_view_mapping_strategy", str(strategy or ""))
        setattr(executor, "_last_recognition_screenshot", screenshot)
        setattr(executor, "_last_recognition_detected", detected)


def _snapshot_mapping_state(executor) -> tuple[Optional[float], Optional[tuple[int, int]]]:
    scale_ratio = getattr(executor, "scale_ratio", None)
    origin_node_pos = getattr(executor, "origin_node_pos", None)
    return scale_ratio, origin_node_pos


def _restore_mapping_state(executor, snapshot: tuple[Optional[float], Optional[tuple[int, int]]]) -> None:
    executor.scale_ratio = snapshot[0]
    executor.origin_node_pos = snapshot[1]


def _try_origin_translation_voting(
    executor,
    screenshot,
    detected,
    mappings,
    log_callback,
) -> Optional[ViewMappingFitResult]:
    origin_samples = _generate_origin_samples(mappings)
    if not origin_samples:
        executor.log("[平移投票] 无可用原点样本，可能缺少共享标题或检测结果为空", log_callback)
        return None

    executor.log(
        f"[平移投票] 原点样本数={len(origin_samples)}，开始网格聚类",
        log_callback,
    )
    candidate_origins = _cluster_origin_samples(origin_samples)
    if not candidate_origins:
        executor.log("[平移投票] 无法从样本中构造原点候选簇", log_callback)
        return None

    region_x: int
    region_y: int
    region_width: int
    region_height: int
    region_x, region_y, region_width, region_height = editor_capture.get_region_rect(
        screenshot,
        "节点图布置区域",
    )
    region_rect: tuple[int, int, int, int] = (
        int(region_x),
        int(region_y),
        int(region_width),
        int(region_height),
    )

    base_tolerance_x, base_tolerance_y = compute_position_thresholds(FIXED_SCALE_RATIO)
    position_tolerance_x = float(base_tolerance_x) * float(ORIGIN_VOTING_POSITION_TOL_MULTIPLIER)
    position_tolerance_y = float(base_tolerance_y) * float(ORIGIN_VOTING_POSITION_TOL_MULTIPLIER)

    best_result: Optional[dict[str, Any]] = None
    best_origin_x: float = 0.0
    best_origin_y: float = 0.0

    for index, (candidate_origin_x, candidate_origin_y, vote_count) in enumerate(
        candidate_origins, start=1
    ):
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
        executor.log(
            f"[平移投票] 候选{index}: origin≈({candidate_origin_x:.1f},{candidate_origin_y:.1f}) "
            f"投票={vote_count} 命中={matched_count} 缺失={missing_count} 得分={score_value:.1f}",
            log_callback,
        )
        if best_result is None or score_value > float(best_result["score"]):
            best_result = evaluation
            best_origin_x = float(candidate_origin_x)
            best_origin_y = float(candidate_origin_y)

    if best_result is None or int(best_result["matched"]) < ORIGIN_VOTING_MIN_INLIERS:
        executor.log(
            f"[平移投票] 校准失败：有效原点候选不足（命中样本 {0 if best_result is None else int(best_result['matched'])}）",
            log_callback,
        )
        return None

    executor.scale_ratio = FIXED_SCALE_RATIO
    executor.origin_node_pos = (int(round(best_origin_x)), int(round(best_origin_y)))
    return ViewMappingFitResult(success=True, strategy=FIT_STRATEGY_ORIGIN_TRANSLATION)


def _try_relative_anchor_unique(
    executor,
    _screenshot,
    _detected,
    mappings,
    log_callback,
) -> Optional[ViewMappingFitResult]:
    executor.log("[视口映射] 尝试退化策略：相对锚点匹配（唯一优先）", log_callback)
    return _try_relative_anchor_alignment(executor, mappings, prefer_unique=True, log_callback=log_callback)


def _try_relative_anchor_any(
    executor,
    _screenshot,
    _detected,
    mappings,
    log_callback,
) -> Optional[ViewMappingFitResult]:
    executor.log("[视口映射] 尝试退化策略：相对锚点匹配（允许非唯一）", log_callback)
    return _try_relative_anchor_alignment(executor, mappings, prefer_unique=False, log_callback=log_callback)


def _try_unique_ratio_alignment_fallback(
    executor,
    screenshot,
    _detected,
    mappings,
    log_callback,
    visual_callback,
) -> Optional[ViewMappingFitResult]:
    unique_titles = collect_unique_titles(
        mappings.shared_names,
        mappings.name_to_model_nodes,
        mappings.name_to_detections,
    )
    ok = try_unique_ratio_alignment(
        executor,
        screenshot,
        unique_titles,
        mappings,
        log_callback,
        visual_callback,
    )
    if not ok:
        return None
    return ViewMappingFitResult(success=True, strategy=FIT_STRATEGY_UNIQUE_RATIO_ALIGNMENT)


def _try_single_anchor_fallback(
    executor,
    screenshot,
    detected,
    mappings,
    log_callback,
) -> Optional[ViewMappingFitResult]:
    executor.log("[视口映射] 尝试退化策略：单锚点匹配", log_callback)
    return _try_single_anchor_mapping(executor, mappings, screenshot, detected, log_callback)


_VIEW_MAPPING_STRATEGIES: tuple[_ViewMappingStrategySpec, ...] = (
    _ViewMappingStrategySpec(
        name="origin_translation_voting",
        allow_when_degraded=False,
        requires_post_validation=False,
        runner=_try_origin_translation_voting,
    ),
    _ViewMappingStrategySpec(
        name="relative_anchor_unique",
        allow_when_degraded=True,
        requires_post_validation=True,
        runner=_try_relative_anchor_unique,
    ),
    _ViewMappingStrategySpec(
        name="relative_anchor_any",
        allow_when_degraded=True,
        requires_post_validation=True,
        runner=_try_relative_anchor_any,
    ),
    _ViewMappingStrategySpec(
        name="unique_ratio_alignment",
        allow_when_degraded=True,
        requires_post_validation=True,
        runner=_try_unique_ratio_alignment_fallback,
    ),
    _ViewMappingStrategySpec(
        name="single_anchor",
        allow_when_degraded=True,
        requires_post_validation=True,
        runner=_try_single_anchor_fallback,
    ),
)


def _run_strategy(
    executor,
    spec: _ViewMappingStrategySpec,
    screenshot,
    detected,
    mappings,
    log_callback,
    visual_callback,
) -> Optional[ViewMappingFitResult]:
    if spec.name == "unique_ratio_alignment":
        return spec.runner(
            executor,
            screenshot,
            detected,
            mappings,
            log_callback,
            visual_callback,
        )
    return spec.runner(
        executor,
        screenshot,
        detected,
        mappings,
        log_callback,
    )


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
        use_strict_window_capture=True,
    )
    if not screenshot:
        executor.log("✗ 截图失败（识别校验）", log_callback)
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

    executor.log(
        f"[识别] 模型节点 {len(mappings.unique_model_names)} 个，检测节点 {len(mappings.unique_detected_names)} 个，"
        f"共同标题 {len(mappings.shared_names)} 个",
        log_callback,
    )

    fit_result: Optional[ViewMappingFitResult] = None
    for spec in _VIEW_MAPPING_STRATEGIES:
        if spec.allow_when_degraded and not allow_degraded_fallback:
            continue
        mapping_snapshot = _snapshot_mapping_state(executor)
        result = _run_strategy(
            executor,
            spec,
            screenshot,
            detected,
            mappings,
            log_callback,
            visual_callback,
        )
        if result is None or not bool(result.success):
            _restore_mapping_state(executor, mapping_snapshot)
            continue

        if spec.requires_post_validation:
            validation = _try_ordinary_nodes_position_match(executor, mappings, log_callback)
            if validation is None or not bool(validation.success):
                executor.log(
                    f"[视口映射] 策略 '{spec.name}' 建立了映射，但普通节点校验失败，继续尝试下一策略",
                    log_callback,
                )
                _restore_mapping_state(executor, mapping_snapshot)
                continue

        fit_result = result
        break

    if fit_result is None or not bool(fit_result.success):
        executor.log(
            "✗ 视口映射失败：所有策略均未能建立稳定映射。建议：移动视口让更多节点完整可见，或调整缩放等级。",
            log_callback,
        )
        return False

    _cache_last_recognition_state(executor, screenshot, detected, fit_result.strategy)
    executor.log(
        f"✓ 视口映射成功：策略={fit_result.strategy} scale={executor.scale_ratio:.4f} "
        f"origin=({executor.origin_node_pos[0]},{executor.origin_node_pos[1]})",
        log_callback,
    )
    return True


