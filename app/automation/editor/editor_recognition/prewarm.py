# -*- coding: utf-8 -*-
"""
editor_recognition.prewarm

截图预热：在连接/执行前提前做一次节点检测，让后续步骤可复用场景快照。
"""

from __future__ import annotations

from app.automation import capture as editor_capture
from app.automation.vision import invalidate_cache, list_nodes


def prepare_for_connect(executor, log_callback=None) -> None:
    screenshot = editor_capture.capture_window_strict(executor.window_title)
    if screenshot is None:
        screenshot = editor_capture.capture_window(executor.window_title)
    if screenshot:
        invalidate_cache()
        detected_nodes = list_nodes(screenshot)
        # 将本次识别结果注入场景快照，便于后续步骤在视口未变化时复用
        get_scene_snapshot = getattr(executor, "get_scene_snapshot", None)
        if callable(get_scene_snapshot) and bool(
            getattr(executor, "enable_scene_snapshot_optimization", True)
        ):
            scene_snapshot = get_scene_snapshot()
            update_method = getattr(scene_snapshot, "update_from_detection", None)
            if callable(update_method):
                update_method(screenshot, detected_nodes)


