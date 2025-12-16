# -*- coding: utf-8 -*-
"""
editor_recognition.view_mapping_geometry_helpers

视口拟合的通用几何辅助函数：
- 将检测框按标题分组并抽取锚点点位（统一使用 bbox 左上角作为锚点）
- 计算模型/检测的全局中心
- 将 MappingData 中的模型节点扁平化
"""

from __future__ import annotations

from typing import Any, Dict

from .models import MappingData


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
            _ = bbox_w, bbox_h
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
    prog_center = (
        (prog_sum_x / prog_count, prog_sum_y / prog_count) if prog_count > 0 else (0.0, 0.0)
    )
    det_center = (det_sum_x / det_count, det_sum_y / det_count) if det_count > 0 else (0.0, 0.0)
    return prog_center, det_center


def _flatten_model_nodes(mappings: MappingData) -> list[dict[str, Any]]:
    all_nodes: list[dict[str, Any]] = []
    for title, nodes in mappings.name_to_model_nodes.items():
        for node in nodes:
            all_nodes.append({"node": node, "title": title})
    return all_nodes


