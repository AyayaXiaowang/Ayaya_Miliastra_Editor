from __future__ import annotations

from typing import List, Optional, Tuple, Dict, Any

from app.automation.vision.ocr_utils import normalize_ocr_bbox
from .reference_panels import compose_reference_panel, build_reference_panel_payload


def build_overlay_for_text_region(
    region_rect: Tuple[int, int, int, int],
    details: Optional[List[Any]],
    *,
    highlight: Optional[Tuple[int, int]] = None,
    highlight_label: str = "",
    extra_rects: Optional[List[Dict[str, Any]]] = None,
    base_label: str = "OCR区域",
    detail_color: Tuple[int, int, int] = (0, 200, 0),
) -> Dict[str, List[Dict[str, Any]]]:
    """根据 OCR 结果构建统一的叠加层结构。"""
    rects: List[Dict[str, Any]] = [
        {
            "bbox": (
                int(region_rect[0]),
                int(region_rect[1]),
                int(region_rect[2]),
                int(region_rect[3]),
            ),
            "color": (0, 120, 255),
            "label": base_label,
        }
    ]
    if details:
        region_x, region_y, _, _ = region_rect
        for item in details:
            box_info = item[0] if len(item) > 0 else None
            label = str(item[1]) if len(item) > 1 else ""
            bbox_left, bbox_top, bbox_width, bbox_height = normalize_ocr_bbox(box_info)
            if bbox_width <= 0 or bbox_height <= 0:
                continue
            rects.append(
                {
                    "bbox": (
                        int(region_x + bbox_left),
                        int(region_y + bbox_top),
                        int(bbox_width),
                        int(bbox_height),
                    ),
                    "color": detail_color,
                    "label": label,
                }
            )
    if highlight is not None:
        rects.append(
            {
                "bbox": (int(highlight[0]) - 10, int(highlight[1]) - 10, 20, 20),
                "color": (255, 180, 0),
                "label": f"点击: {highlight_label}" if highlight_label else "点击",
            }
        )
    if extra_rects:
        rects.extend(extra_rects)
    return {"rects": rects}

