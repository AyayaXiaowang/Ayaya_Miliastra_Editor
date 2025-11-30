from __future__ import annotations

from typing import Optional, Tuple
from PIL import Image

from .cache import get_enforce_graph_roi
from .roi_config import get_region_rect, clip_to_graph_region
from .emitters import emit_log_message

Region = Tuple[int, int, int, int]


def _format_rect(rect: Region | None) -> str:
    if rect is None:
        return "(None)"
    x, y, w, h = rect
    return f"({int(x)},{int(y)},{int(w)},{int(h)})"


def resolve_search_region(
    screenshot: Image.Image,
    search_region: Optional[Region],
    *,
    log_label: str,
) -> Optional[Region]:
    """根据强制节点图设置，返回最终用于匹配的搜索区域。

    当未开启强制 ROI 时，直接返回传入区域（允许 None 表示全图）。
    """
    normalized = tuple(int(v) for v in search_region) if search_region else None
    if not get_enforce_graph_roi():
        return normalized

    graph_rect = tuple(int(v) for v in get_region_rect(screenshot, "节点图布置区域"))
    if normalized is None:
        emit_log_message(
            f"{log_label} 限定至节点图区域: 原=(全图) 节点图={_format_rect(graph_rect)} → 实际={_format_rect(graph_rect)}"
        )
        return graph_rect

    limited = clip_to_graph_region(screenshot, normalized, graph_rect=graph_rect)
    emit_log_message(
        f"{log_label} 限定至节点图区域: 原={_format_rect(normalized)} 节点图={_format_rect(graph_rect)} → 实际={_format_rect(limited)}"
    )
    return limited


def clip_region_with_graph(
    screenshot: Image.Image,
    region: Region,
    *,
    log_label: str,
) -> Region:
    """当启用强制 ROI 时，将区域裁剪到节点图并记录日志。"""
    base = tuple(int(v) for v in region)
    if not get_enforce_graph_roi():
        return base

    graph_rect = tuple(int(v) for v in get_region_rect(screenshot, "节点图布置区域"))
    clipped = clip_to_graph_region(screenshot, base, graph_rect=graph_rect)
    emit_log_message(
        f"{log_label} 限定至节点图区域: 原={_format_rect(base)} 节点图={_format_rect(graph_rect)} → 实际={_format_rect(clipped)}"
    )
    return clipped

