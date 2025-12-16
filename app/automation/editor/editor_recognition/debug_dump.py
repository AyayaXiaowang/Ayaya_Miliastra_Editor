# -*- coding: utf-8 -*-
"""
editor_recognition.debug_dump

调试落盘：将识别阶段使用到的原始检测结果输出为 JSON，便于离线复现与分析。
"""

from __future__ import annotations

from pathlib import Path

from engine.graph.models.graph_model import GraphModel
from engine.utils.cache.cache_paths import get_runtime_cache_root


def _dump_last_focus_detection_snapshot(
    executor,
    graph_model: GraphModel,
    detected: list,
) -> None:
    """
    将最近一次用于视口拟合的原始检测结果落盘为 JSON，便于离线分析。

    仅包含“截图中识别到的节点名字与坐标”，不涉及模型 node_id：
    - 路径：{runtime_cache_root}/debug/last_focus_detection.json（默认 runtime_cache_root 为 app/runtime/cache）
    - 字段：graph_id、每个检测框的中文标题与编辑器坐标 bbox。
    """
    workspace_path_value = getattr(executor, "workspace_path", None)
    if workspace_path_value is None:
        return
    workspace_root = Path(workspace_path_value)
    output_dir = get_runtime_cache_root(workspace_root) / "debug"
    output_dir.mkdir(parents=True, exist_ok=True)

    graph_id_value = getattr(graph_model, "graph_id", None)
    graph_id_text = str(graph_id_value) if graph_id_value is not None else ""

    detections_payload: list[dict] = []
    for detection in detected:
        bbox_x, bbox_y, bbox_w, bbox_h = detection.bbox
        raw_name_cn = str(getattr(detection, "name_cn", "") or "")
        title_cn = ""
        extract_method = getattr(executor, "extract_chinese", None)
        if callable(extract_method):
            title_cn = extract_method(raw_name_cn)
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


