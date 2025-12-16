# -*- coding: utf-8 -*-
"""
EditorExecutor Visual Mixin

收敛截图 + 叠加层 + 推送到监控面板的统一入口逻辑。
"""

from __future__ import annotations

from io import BytesIO
from typing import Callable, Optional

from PIL import Image

from app.automation import capture as editor_capture
from app.automation.capture.reference_panels import compose_reference_panel
from app.automation.input.common import build_graph_region_overlay


class EditorExecutorVisualMixin:
    window_title: str

    # === 统一可视化输出 ===
    def _build_reference_panel_image(
        self,
        screenshot: Image.Image,
        overlays: Optional[dict],
    ) -> Image.Image:
        """基于 overlays 中的 reference_panel 信息构造带参考面板的截图。

        会在 overlays['reference_panel'] 上打 '_embedded' 标记，以避免在同一帧重复合成。
        """
        screenshot_to_emit = screenshot
        if not isinstance(overlays, dict):
            return screenshot_to_emit
        panel_payload = overlays.get("reference_panel")
        if not isinstance(panel_payload, dict) or panel_payload.get("_embedded"):
            return screenshot_to_emit

        content_image = None
        image_bytes = panel_payload.get("image_bytes")
        if isinstance(image_bytes, (bytes, bytearray)) and len(image_bytes) > 0:
            try:
                with Image.open(BytesIO(image_bytes)) as tpl_img:
                    content_image = tpl_img.copy()
            except Exception:
                content_image = None

        if content_image is None:
            image_path = panel_payload.get("image_path")
            if image_path:
                try:
                    with Image.open(image_path) as tpl_img_path:
                        content_image = tpl_img_path.copy()
                except Exception:
                    content_image = None

        if content_image is None:
            return screenshot_to_emit

        screenshot_to_emit = compose_reference_panel(
            screenshot,
            title=str(panel_payload.get("title", "") or ""),
            content_text=panel_payload.get("text"),
            content_image=content_image,
        )
        panel_payload["_embedded"] = True
        return screenshot_to_emit

    def _emit_visual(self, screenshot: Image.Image, overlays: Optional[dict], visual_callback) -> None:
        """统一的可视化输出入口：所有涉及截图的步骤通过此方法将叠加层推送到监控面板。
        overlays 结构：{'rects': [...], 'circles': [...]}，与 UI 层保持一致。
        """
        screenshot_to_emit = self._build_reference_panel_image(screenshot, overlays)
        if visual_callback is not None:
            visual_callback(screenshot_to_emit, overlays)

    def capture_and_emit(
        self,
        label: str = "",
        overlays_builder: Optional[Callable[[Image.Image], Optional[dict]]] = None,
        visual_callback=None,
        *,
        use_strict_window_capture: bool = False,
    ) -> Image.Image:
        """一次性完成：窗口截图 → 叠加区域 → 推送到监控。

        规范：至少叠加"节点图布置区域"矩形；调用方可通过 overlays_builder 追加叠加内容。
        返回本次截图，以便调用方继续使用。
        """
        if use_strict_window_capture:
            screenshot = editor_capture.capture_window_strict(self.window_title)
            if screenshot is None:
                screenshot = editor_capture.capture_window(self.window_title)
        else:
            screenshot = editor_capture.capture_window(self.window_title)
        if not screenshot:
            raise ValueError("截图失败")

        base_overlay = build_graph_region_overlay(screenshot)
        rects = list(base_overlay.get("rects", []))
        if label and rects:
            rects[0]["label"] = f"{rects[0]['label']} · {label}"
        circles = []
        reference_panel_payload = None
        if overlays_builder is not None:
            extra = overlays_builder(screenshot)
            if isinstance(extra, dict):
                if isinstance(extra.get("rects"), list):
                    rects.extend(extra["rects"])
                if isinstance(extra.get("circles"), list):
                    circles.extend(extra["circles"])
                if "reference_panel" in extra and reference_panel_payload is None:
                    reference_panel_payload = extra["reference_panel"]
        overlays = {"rects": rects}
        if circles:
            overlays["circles"] = circles
        if reference_panel_payload:
            overlays["reference_panel"] = reference_panel_payload
        self._emit_visual(screenshot, overlays, visual_callback)
        return screenshot

    def emit_visual(
        self,
        screenshot: Image.Image,
        overlays: Optional[dict],
        visual_callback,
    ) -> None:
        """
        公开的可视化输出接口：语义与 `_emit_visual` 一致。

        跨模块调用推荐使用本方法，而不是直接访问私有实现。
        """
        self._emit_visual(screenshot, overlays, visual_callback)


