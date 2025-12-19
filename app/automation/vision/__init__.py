"""
统一的视觉识别门面（Facade）。

目的：
- 为运行时自动化与 CLI 提供统一的视觉识别入口，避免跨层耦合；
- 对外暴露稳定 API：节点/端口识别、缓存失效、标题映射日志、相位相关位移等。

注意：
- 不增加异常吞噬；保持与底层实现一致的行为；
- 仅做轻薄转发，便于未来替换底层实现。
"""

from __future__ import annotations

import math
from typing import List, Tuple, Optional, Any, Dict

from PIL import Image

from . import vision_backend as _vb
from app.automation.capture import capture_client_image as _capture_client_image

from .ui_profile_params import get_port_header_height_px as _get_port_header_height_px

_NODE_GRID_SIZE = 256
_DUPLICATE_IOU_THRESHOLD = 0.35
_DUPLICATE_CONTAINMENT_RATIO = 0.85
_DUPLICATE_CENTER_DISTANCE_PX = 28.0
_DUPLICATE_AXIS_OVERLAP_RATIO = 0.65
_last_node_filter_report: Optional[Dict[str, Any]] = None


def get_port_recognition_header_height_px() -> int:
    """返回当前环境下端口识别应跳过的节点标题栏高度（像素）。"""
    return int(_get_port_header_height_px())


def _round4(value: float) -> float:
    return float(round(value, 4))


def _area(bbox: Tuple[int, int, int, int]) -> int:
    return int(max(0, int(bbox[2])) * max(0, int(bbox[3])))


def _calc_overlap_metrics(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> Dict[str, float]:
    ax, ay, aw, ah = int(box_a[0]), int(box_a[1]), int(box_a[2]), int(box_a[3])
    bx, by, bw, bh = int(box_b[0]), int(box_b[1]), int(box_b[2]), int(box_b[3])
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return {
            "intersection_area": 0.0,
            "iou": 0.0,
            "containment_ratio": 0.0,
            "center_distance": float("inf"),
            "horizontal_overlap_ratio": 0.0,
            "vertical_overlap_ratio": 0.0,
        }
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    inter_w = max(0, right - left)
    inter_h = max(0, bottom - top)
    intersection_area = float(inter_w * inter_h)
    area_a = float(aw * ah)
    area_b = float(bw * bh)
    union_area = max(area_a + area_b - intersection_area, 1.0)
    min_area = min(area_a, area_b)
    center_ax = ax + aw / 2.0
    center_ay = ay + ah / 2.0
    center_bx = bx + bw / 2.0
    center_by = by + bh / 2.0
    center_distance = math.sqrt((center_ax - center_bx) ** 2 + (center_ay - center_by) ** 2)
    horizontal_overlap_ratio = float(inter_w) / float(min(aw, bw)) if min(aw, bw) > 0 else 0.0
    vertical_overlap_ratio = float(inter_h) / float(min(ah, bh)) if min(ah, bh) > 0 else 0.0
    containment_ratio = (intersection_area / min_area) if min_area > 0 else 0.0
    iou = intersection_area / union_area if union_area > 0 else 0.0
    return {
        "intersection_area": intersection_area,
        "iou": iou,
        "containment_ratio": containment_ratio,
        "center_distance": center_distance,
        "horizontal_overlap_ratio": horizontal_overlap_ratio,
        "vertical_overlap_ratio": vertical_overlap_ratio,
    }


def _should_suppress_duplicate(metrics: Dict[str, float]) -> Tuple[bool, Optional[str]]:
    if metrics["intersection_area"] <= 0:
        return False, None
    if metrics["iou"] >= _DUPLICATE_IOU_THRESHOLD:
        return True, "iou"
    if metrics["containment_ratio"] >= _DUPLICATE_CONTAINMENT_RATIO:
        return True, "containment"
    if (
        metrics["center_distance"] <= _DUPLICATE_CENTER_DISTANCE_PX
        and metrics["horizontal_overlap_ratio"] >= _DUPLICATE_AXIS_OVERLAP_RATIO
        and metrics["vertical_overlap_ratio"] >= _DUPLICATE_AXIS_OVERLAP_RATIO
    ):
        return True, "center_overlap"
    return False, None

def list_nodes(canvas_image: Image.Image):
    """返回识别到的节点列表（含中文名与矩形）。

    根源层去重：任意交叠即抑制（面积优先），仅保留较大的一个，
    以避免上层叠加与匹配阶段出现重复框。
    """
    global _last_node_filter_report
    detections = _vb.list_nodes(canvas_image)

    report: Dict[str, Any] = {
        "raw_count": int(len(detections)),
        "kept_count": 0,
        "kept": [],
        "suppressed": [],
    }

    indexed: List[Tuple[Any, Tuple[int, int, int, int], int]] = []
    for det in detections:
        bx, by, bw, bh = getattr(det, "bbox")
        box_tuple = (int(bx), int(by), int(bw), int(bh))
        indexed.append((det, box_tuple, _area(box_tuple)))
    indexed.sort(key=lambda item: item[2], reverse=True)

    kept: List[Any] = []
    kept_boxes: List[Tuple[int, int, int, int]] = []
    cell_map: dict[Tuple[int, int], List[int]] = {}

    def _register_cells(index: int, bbox: Tuple[int, int, int, int]) -> None:
        min_cell_x = int(bbox[0] // _NODE_GRID_SIZE)
        max_cell_x = int((bbox[0] + bbox[2]) // _NODE_GRID_SIZE)
        min_cell_y = int(bbox[1] // _NODE_GRID_SIZE)
        max_cell_y = int((bbox[1] + bbox[3]) // _NODE_GRID_SIZE)
        for gx in range(min_cell_x, max_cell_x + 1):
            for gy in range(min_cell_y, max_cell_y + 1):
                cell_map.setdefault((gx, gy), []).append(index)

    for det, box, current_area in indexed:
        min_cell_x = int(box[0] // _NODE_GRID_SIZE)
        max_cell_x = int((box[0] + box[2]) // _NODE_GRID_SIZE)
        min_cell_y = int(box[1] // _NODE_GRID_SIZE)
        max_cell_y = int((box[1] + box[3]) // _NODE_GRID_SIZE)
        overlapped = False
        overlap_target_index: Optional[int] = None
        overlap_metrics: Optional[Dict[str, float]] = None
        overlap_reason: Optional[str] = None
        for gx in range(min_cell_x, max_cell_x + 1):
            for gy in range(min_cell_y, max_cell_y + 1):
                for existing_idx in cell_map.get((gx, gy), []):
                    metrics = _calc_overlap_metrics(box, kept_boxes[existing_idx])
                    should_suppress, reason = _should_suppress_duplicate(metrics)
                    if should_suppress:
                        overlapped = True
                        overlap_target_index = existing_idx
                        overlap_metrics = metrics
                        overlap_reason = reason
                        break
                if overlapped:
                    break
            if overlapped:
                break
        if overlapped:
            overlap_title = ""
            overlap_bbox: Optional[Tuple[int, int, int, int]] = None
            if overlap_target_index is not None:
                overlap_target = kept[overlap_target_index]
                overlap_title = str(getattr(overlap_target, "name_cn", "") or "")
                overlap_bbox = kept_boxes[overlap_target_index]
            report["suppressed"].append(
                {
                    "title_cn": str(getattr(det, "name_cn", "") or ""),
                    "bbox": box,
                    "area": int(current_area),
                    "reason": str(overlap_reason or "overlap"),
                    "overlap_target_title": overlap_title,
                    "overlap_target_bbox": overlap_bbox,
                    "overlap_metrics": None
                    if overlap_metrics is None
                    else {
                        "iou": _round4(overlap_metrics.get("iou", 0.0)),
                        "containment_ratio": _round4(overlap_metrics.get("containment_ratio", 0.0)),
                        "center_distance": _round4(overlap_metrics.get("center_distance", 0.0)),
                        "horizontal_overlap_ratio": _round4(overlap_metrics.get("horizontal_overlap_ratio", 0.0)),
                        "vertical_overlap_ratio": _round4(overlap_metrics.get("vertical_overlap_ratio", 0.0)),
                    },
                }
            )
            continue
        kept.append(det)
        kept_boxes.append(box)
        _register_cells(len(kept_boxes) - 1, box)

    report["kept_count"] = len(kept)
    report["kept"] = [
        {
            "title_cn": str(getattr(kept[idx], "name_cn", "") or ""),
            "bbox": kept_boxes[idx],
            "area": _area(kept_boxes[idx]),
        }
        for idx in range(len(kept))
    ]
    _last_node_filter_report = report
    return kept


def list_ports(canvas_image: Image.Image, node_bbox: Tuple[int, int, int, int]):
    """返回指定节点矩形内识别到的端口列表。"""
    return _vb.list_ports(canvas_image, node_bbox)


def invalidate_cache() -> None:
    """失效一步式识别缓存。"""
    _vb.invalidate_cache()


def phase_correlation_delta(prev_image: Image.Image, next_image: Image.Image) -> Tuple[float, float]:
    """估计两帧图像的内容位移（像素）。"""
    return _vb.phase_correlation_delta(prev_image, next_image)


def get_last_raw_titles() -> List[str]:
    """返回最近一次识别到的原始中文标题（可重复）。"""
    return _vb.get_last_raw_titles()


def get_last_raw_title_rects() -> List[Tuple[int, int, int, int]]:
    """返回最近一次识别到的中文标题矩形列表（与 get_last_raw_titles 对齐）。"""
    return _vb.get_last_raw_title_rects()


def get_and_clear_title_mapping_logs() -> List[dict]:
    """返回并清空最近的标题近似映射日志。"""
    return _vb.get_and_clear_title_mapping_logs()


def get_template_dir() -> str:
    """返回模板资源目录路径。"""
    return _vb.get_template_dir()


def capture_client_image(hwnd: int) -> Image.Image:
    """转发：截取指定窗口客户区图像。

    推荐从 `app.automation.capture.capture_client_image` 直接导入使用，此处仅作为转发入口。
    """
    return _capture_client_image(hwnd)


def get_last_node_filter_report() -> Dict[str, Any]:
    """返回最近一次 list_nodes 执行时的去重统计。"""
    if _last_node_filter_report is None:
        return {
            "raw_count": 0,
            "kept_count": 0,
            "kept": [],
            "suppressed": [],
        }
    return dict(_last_node_filter_report)


__all__ = [
    "list_nodes",
    "list_ports",
    "invalidate_cache",
    "phase_correlation_delta",
    "get_last_raw_titles",
    "get_last_raw_title_rects",
    "get_and_clear_title_mapping_logs",
    "get_template_dir",
    "capture_client_image",
    "get_last_node_filter_report",
]

