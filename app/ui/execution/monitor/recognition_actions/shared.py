# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
from typing import Optional

from app.automation.input.common import clear_log_sink as _clear_log_sink
from app.automation.input.common import clear_visual_sink as _clear_visual_sink
from app.automation.input.common import set_log_sink as _set_log_sink
from app.automation.input.common import set_visual_sink as _set_visual_sink
from app.automation.vision.scene_recognizer import TemplateMatchDebugInfo


@contextmanager
def _temporary_global_sinks(update_visual_callback, log_callback):
    """临时将监控面板注册为全局可视化/日志汇聚器，并确保最终清理。

    说明：部分底层 OCR/模板匹配工具会通过全局 sink 推送叠加画面与日志。
    若中途抛异常未清理，会导致后续监控输出串台，因此必须保证 finally 清理。
    """
    _set_visual_sink(update_visual_callback)
    _set_log_sink(log_callback)
    try:
        yield
    finally:
        _clear_visual_sink()
        _clear_log_sink()


def _is_overlapped_same_template_suppressed_nms(
    entry: TemplateMatchDebugInfo,
    all_entries: list[TemplateMatchDebugInfo],
) -> bool:
    """判断条目是否为“同一模板、发生重叠且已被 NMS 抑制”的候选。

    这类候选在“深度端口识别”中只在统计与日志中体现，画面上仅展示同一模板中置信度最高的一个。
    """
    if entry.suppression_kind != "nms":
        return False
    if entry.overlap_target_bbox is None:
        return False
    for candidate in all_entries:
        if candidate.status != "kept":
            continue
        if candidate.template_name != entry.template_name:
            continue
        if candidate.bbox != entry.overlap_target_bbox:
            continue
        if float(candidate.confidence) >= float(entry.confidence):
            return True
    return False


def _find_overlap_target_for_suppressed_nms(
    entry: TemplateMatchDebugInfo,
    all_entries: list[TemplateMatchDebugInfo],
) -> Optional[TemplateMatchDebugInfo]:
    """查找导致当前 NMS 抑制条目的“获胜候选”，用于在标签中显示重叠对象。

    优先返回同模板的获胜命中；若未找到同模板，则回退为任意模板中与 overlap_target_bbox 匹配且置信度最高的保留候选。
    """
    if entry.suppression_kind != "nms":
        return None
    if entry.overlap_target_bbox is None:
        return None

    preferred_candidate: Optional[TemplateMatchDebugInfo] = None
    fallback_candidate: Optional[TemplateMatchDebugInfo] = None
    for candidate in all_entries:
        if candidate.bbox != entry.overlap_target_bbox:
            continue

        if candidate.template_name == entry.template_name:
            if preferred_candidate is None or float(candidate.confidence) > float(preferred_candidate.confidence):
                preferred_candidate = candidate
        elif fallback_candidate is None or float(candidate.confidence) > float(fallback_candidate.confidence):
            fallback_candidate = candidate

    return preferred_candidate or fallback_candidate


__all__ = [
    "_find_overlap_target_for_suppressed_nms",
    "_is_overlapped_same_template_suppressed_nms",
    "_temporary_global_sinks",
]



