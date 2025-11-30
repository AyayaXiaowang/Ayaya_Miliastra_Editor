from __future__ import annotations

"""
统一的 capture 层可视化/日志发布工具。

职责：
- 将 OCR、模板匹配等模块的叠加层输出统一委托到 input.common 注册的 sink；
- 避免在各子模块重复定义 `_emit_global_visual/_emit_global_log`。
"""

from typing import Optional, Dict, Any
from io import BytesIO
from PIL import Image

from ..input.common import get_visual_sink, get_log_sink
from .reference_panels import compose_reference_panel


def _embed_reference_panel_if_needed(
    base_image: Image.Image,
    overlays: Optional[Dict[str, Any]],
) -> Image.Image:
    if not isinstance(overlays, dict):
        return base_image
    panel_payload = overlays.get('reference_panel')
    if not isinstance(panel_payload, dict):
        return base_image
    if panel_payload.get('_embedded'):
        return base_image
    content_image = None
    image_bytes = panel_payload.get('image_bytes')
    if isinstance(image_bytes, (bytes, bytearray)) and len(image_bytes) > 0:
        try:
            with Image.open(BytesIO(image_bytes)) as tpl_img:
                content_image = tpl_img.copy()
        except Exception:
            content_image = None
    if content_image is None:
        image_path = panel_payload.get('image_path')
        if image_path:
            try:
                with Image.open(image_path) as tpl_path_img:
                    content_image = tpl_path_img.copy()
            except Exception:
                content_image = None
    if content_image is None:
        return base_image
    panel_payload['_embedded'] = True
    return compose_reference_panel(
        base_image,
        title=str(panel_payload.get('title', '') or ''),
        content_text=panel_payload.get('text'),
        content_image=content_image,
    )


def emit_visual_overlay(base_image: Image.Image, overlays: Optional[Dict[str, Any]]) -> None:
    """推送可视化信息到全局监控面板。"""
    sink = get_visual_sink()
    if sink is not None:
        processed_image = _embed_reference_panel_if_needed(base_image, overlays)
        sink(processed_image, overlays)


def emit_log_message(message: str) -> None:
    """推送文本日志到全局监控面板。"""
    sink = get_log_sink()
    if sink is not None:
        sink(str(message))

