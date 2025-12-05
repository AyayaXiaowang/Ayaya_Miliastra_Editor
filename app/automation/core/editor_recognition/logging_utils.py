# -*- coding: utf-8 -*-
"""
editor_recognition.logging_utils

与识别阶段的日志和可视化输出相关的工具函数。
"""

from __future__ import annotations

from PIL import Image

from app.automation import capture as editor_capture
from app.automation.vision import get_last_raw_title_rects as _get_raw_title_rects


def log_detection_snapshot(
    executor,
    screenshot: Image.Image,
    detected,
    log_callback,
    visual_callback,
) -> None:
    raw_title_rects = _get_raw_title_rects()
    raw_titles = [str(item[0]) for item in raw_title_rects]
    executor.log(f"[识别] 原始标题(中文，仅OCR，不映射) {len(raw_titles)}: {raw_titles}", log_callback)
    from app.automation.vision import get_and_clear_title_mapping_logs as _get_title_logs

    title_logs = _get_title_logs()

    executor.log(f"[识别] 窗口内节点数: {int(len(detected))}", log_callback)
    det_titles = [executor.extract_chinese(getattr(node, 'name_cn', '') or '') for node in detected]
    nonempty_cnt = sum(1 for title in det_titles if title)
    empty_cnt = int(len(det_titles) - nonempty_cnt)
    executor.log(f"[识别] 识别标题：中文非空 {nonempty_cnt} 项，空标题 {empty_cnt} 项", log_callback)
    full_scene_names = [title for title in det_titles if title]
    executor.log(f"[识别] 场景中文名(全量) {len(full_scene_names)}: {full_scene_names}", log_callback)

    rects_detected = []
    rx0, ry0, rw0, rh0 = editor_capture.get_region_rect(screenshot, "节点图布置区域")
    rects_detected.append(
        {'bbox': (int(rx0), int(ry0), int(rw0), int(rh0)), 'color': (120, 180, 255), 'label': '节点图布置区域'}
    )
    for node in detected:
        bbox_x, bbox_y, bbox_w, bbox_h = node.bbox
        label_cn = executor.extract_chinese(getattr(node, 'name_cn', '') or '')
        rects_detected.append({'bbox': (int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h)), 'color': (120, 200, 255), 'label': str(label_cn)})
    if rects_detected and visual_callback is not None:
        visual_callback(screenshot, {'rects': rects_detected})

