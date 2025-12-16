# -*- coding: utf-8 -*-
"""
editor_recognition.view_mapping_single_anchor

单锚点退化映射：
在原点投票失败且缺少足够结构信息时，使用一个“程序节点 ↔ 检测框”配对估算 origin。
"""

from __future__ import annotations

from typing import Optional

from PIL import Image

from app.automation.editor.editor_mapping import FIXED_SCALE_RATIO
from app.automation.editor.ui_constants import NODE_VIEW_HEIGHT_PX, NODE_VIEW_WIDTH_PX

from .constants import FIT_STRATEGY_SINGLE_ANCHOR
from .models import MappingData, ViewMappingFitResult
from .view_mapping_geometry_helpers import _build_detection_centers_by_title


def _try_single_anchor_mapping(
    executor,
    mappings: MappingData,
    screenshot: Image.Image,
    detected: list,
    log_callback,
) -> Optional[ViewMappingFitResult]:
    """
    在原点平移投票失败时，基于单个锚点节点建立退化视口映射。

    约定：
    - 仅依赖一个“程序节点 ↔ 检测框”配对来估算原点平移；
    - 缩放比例仍固定为 1.0，只将锚点估计的缩放用于环境健康检查与日志；
    - 优先选择“模型与检测均唯一”的标题作为锚点，其次退回到任意共享标题。
    """
    centers_by_title = _build_detection_centers_by_title(mappings)
    if not centers_by_title:
        executor.log("[单锚点] 当前画面无可用检测节点，无法建立退化视口映射", log_callback)
        return None

    candidate_titles: list[str] = []
    for name in mappings.shared_names:
        model_nodes = mappings.name_to_model_nodes.get(name, [])
        det_centers = centers_by_title.get(name, [])
        if not model_nodes or not det_centers:
            continue
        candidate_titles.append(name)

    if not candidate_titles:
        executor.log("[单锚点] 当前画面与图模型之间无共享标题，无法建立退化视口映射", log_callback)
        return None

    def _title_sort_key(title: str) -> tuple[int, int]:
        models = mappings.name_to_model_nodes.get(title, [])
        detections = centers_by_title.get(title, [])
        is_unique_model = len(models) == 1
        is_unique_detection = len(detections) == 1
        # 唯一模型+唯一检测优先，其次按“模型+检测数量”从少到多
        uniqueness_rank = 0 if (is_unique_model and is_unique_detection) else 1
        count_score = len(models) + len(detections)
        return (uniqueness_rank, count_score)

    candidate_titles.sort(key=_title_sort_key)
    anchor_title = candidate_titles[0]
    model_nodes_for_title = mappings.name_to_model_nodes.get(anchor_title, [])
    det_centers_for_title = centers_by_title.get(anchor_title, [])
    if not model_nodes_for_title or not det_centers_for_title:
        executor.log("[单锚点] 选定锚点标题缺少模型或检测数据，放弃退化映射", log_callback)
        return None

    anchor_model = model_nodes_for_title[0]
    anchor_detection = det_centers_for_title[0]
    bbox_x, bbox_y, bbox_w, bbox_h = anchor_detection["bbox"]

    program_node_width = NODE_VIEW_WIDTH_PX
    program_node_height = NODE_VIEW_HEIGHT_PX
    scale_x = float(bbox_w) / program_node_width if bbox_w > 0 else 0.0
    scale_y = float(bbox_h) / program_node_height if bbox_h > 0 else 0.0
    if scale_x <= 0.0 or scale_y <= 0.0:
        executor.log("[单锚点] 锚点识别结果异常：节点尺寸为 0，无法估算缩放比例", log_callback)
        return None

    avg_scale = (scale_x + scale_y) * 0.5
    if avg_scale <= 1e-6:
        executor.log("[单锚点] 锚点识别结果异常：估算缩放比例过小", log_callback)
        return None

    executor.scale_ratio = FIXED_SCALE_RATIO

    anchor_prog_x = float(anchor_model.pos[0])
    anchor_prog_y = float(anchor_model.pos[1])
    origin_x = float(bbox_x) - anchor_prog_x * float(executor.scale_ratio)
    origin_y = float(bbox_y) - anchor_prog_y * float(executor.scale_ratio)
    executor.origin_node_pos = (int(round(origin_x)), int(round(origin_y)))

    expected_scale = float(FIXED_SCALE_RATIO)
    scale_deviation = abs(avg_scale - expected_scale)
    if scale_deviation >= 0.10:
        executor.log(
            f"· 环境检查：检测到锚点缩放≈{avg_scale:.4f}，与固定比例 {expected_scale:.4f} 差异较大，"
            f"请检查系统显示缩放与编辑器节点图缩放是否满足预期",
            log_callback,
        )

    executor.log(
        f"✓ 单锚点匹配成功：锚点 '{anchor_title}' scale_est≈{avg_scale:.4f} → 固定 {executor.scale_ratio:.2f} "
        f"origin=({executor.origin_node_pos[0]},{executor.origin_node_pos[1]})",
        log_callback,
    )

    fit_result = ViewMappingFitResult(success=True, strategy=FIT_STRATEGY_SINGLE_ANCHOR)
    if hasattr(executor, "__dict__"):
        setattr(executor, "_last_view_mapping_strategy", fit_result.strategy)
        setattr(executor, "_last_recognition_screenshot", screenshot)
        setattr(executor, "_last_recognition_detected", detected)
    return fit_result


