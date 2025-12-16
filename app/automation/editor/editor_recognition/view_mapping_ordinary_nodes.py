# -*- coding: utf-8 -*-
"""
editor_recognition.view_mapping_ordinary_nodes

普通节点位置匹配兜底逻辑：在已有 scale_ratio + origin 的前提下，用共享标题节点验证映射是否可信。
"""

from __future__ import annotations

from typing import Optional

from app.automation.input.common import compute_position_thresholds

from .constants import (
    FIT_STRATEGY_ORDINARY_NODES,
    ORDINARY_NODES_MIN_MATCHES,
    ORDINARY_NODES_POSITION_TOLERANCE_MULTIPLIER,
)
from .models import MappingData, ViewMappingFitResult


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
        executor.log("[普通节点] 坐标未校准，无法进行位置匹配", log_callback)
        return None

    scale_ratio = float(executor.scale_ratio)
    origin_x = float(executor.origin_node_pos[0])
    origin_y = float(executor.origin_node_pos[1])

    pos_threshold_x, pos_threshold_y = compute_position_thresholds(scale_ratio)
    pos_threshold_x *= ORDINARY_NODES_POSITION_TOLERANCE_MULTIPLIER
    pos_threshold_y *= ORDINARY_NODES_POSITION_TOLERANCE_MULTIPLIER

    executor.log(
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
                    matched_nodes.append(
                        (
                            name,
                            prog_x,
                            prog_y,
                            det_left,
                            det_top,
                            (delta_x * delta_x + delta_y * delta_y) ** 0.5,
                        )
                    )
                    executor.log(
                        f"  [匹配{len(matched_nodes)}] '{name}': prog=({prog_x:.1f},{prog_y:.1f}) "
                        f"→ 预期=({expected_x:.1f},{expected_y:.1f}) vs 检测=({det_left:.1f},{det_top:.1f}) "
                        f"偏差=({delta_x:.1f},{delta_y:.1f})px",
                        log_callback,
                    )
                    break

    executor.log(
        f"[普通节点] 匹配完成：共匹配 {len(matched_nodes)} 个节点（需要≥{ORDINARY_NODES_MIN_MATCHES}）",
        log_callback,
    )

    if len(matched_nodes) >= ORDINARY_NODES_MIN_MATCHES:
        executor.log(
            f"✓ 普通节点位置匹配成功：{len(matched_nodes)} 个节点匹配，视口校准完成",
            log_callback,
        )
        return ViewMappingFitResult(success=True, strategy=FIT_STRATEGY_ORDINARY_NODES)

    executor.log(
        f"✗ 普通节点匹配不足：仅匹配 {len(matched_nodes)} 个节点，无法确认视口",
        log_callback,
    )
    executor.log(
        "  · 建议：移动视口让更多节点完整可见，或放大图形/调整缩放等级",
        log_callback,
    )
    return None


