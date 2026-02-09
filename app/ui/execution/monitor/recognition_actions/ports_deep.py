# -*- coding: utf-8 -*-
from __future__ import annotations

from app.automation import AutomationFacade
from app.automation import capture as editor_capture
from app.automation.vision import get_port_recognition_header_height_px
from app.automation.vision import get_template_dir as _vision_get_template_dir
from app.automation.vision import list_nodes as _vision_list_nodes
from app.automation.vision.scene_recognizer import (
    TemplateMatchDebugInfo,
    debug_match_templates_for_rectangle,
)

from .shared import _find_overlap_target_for_suppressed_nms, _is_overlapped_same_template_suppressed_nms


def test_ports_deep(self) -> None:
    """深度端口识别：在基础端口识别上展示模板去重前后的所有候选与被排除原因。"""
    facade = AutomationFacade()
    screenshot = facade.capture_window(self._get_window_title())
    if not screenshot:
        self._log("✗ 深度端口识别测试失败：未找到目标窗口")
        return

    region_x, region_y, region_w, region_h = editor_capture.get_region_rect(screenshot, "节点图布置区域")
    canvas_image = screenshot.crop(
        (
            int(region_x),
            int(region_y),
            int(region_x + region_w),
            int(region_y + region_h),
        )
    )
    template_dir = _vision_get_template_dir()
    nodes = _vision_list_nodes(screenshot)
    rects: list[dict] = []
    total_template_matches = 0
    total_suppressed_matches = 0
    suppressed_preview_snippets: list[str] = []

    for node_item in nodes:
        node_bbox_x, node_bbox_y, node_bbox_w, node_bbox_h = node_item.bbox
        node_label = str(getattr(node_item, "name_cn", "") or "")
        rects.append(
            {
                "bbox": (
                    int(node_bbox_x),
                    int(node_bbox_y),
                    int(node_bbox_w),
                    int(node_bbox_h),
                ),
                "color": (140, 160, 255),
                "label": node_label,
            }
        )
        excluded_height_px = min(int(node_bbox_h), int(get_port_recognition_header_height_px()))
        if excluded_height_px > 0:
            rects.append(
                {
                    "bbox": (
                        int(node_bbox_x),
                        int(node_bbox_y),
                        int(node_bbox_w),
                        int(excluded_height_px),
                    ),
                    "color": (255, 0, 0),
                    "label": f"端口排除区({int(excluded_height_px)}px)",
                }
            )

        rect_canvas = {
            "x": int(node_bbox_x) - int(region_x),
            "y": int(node_bbox_y) - int(region_y),
            "width": int(node_bbox_w),
            "height": int(node_bbox_h),
        }

        template_debug_list = debug_match_templates_for_rectangle(
            canvas_image,
            rect_canvas,
            template_dir,
            header_height=int(get_port_recognition_header_height_px()),
            threshold=0.7,
        )

        best_suppressed_nms_map: dict[tuple[str, tuple[int, int, int, int]], TemplateMatchDebugInfo] = {}
        for candidate_entry in template_debug_list:
            if candidate_entry.suppression_kind != "nms":
                continue
            overlap_target_bbox_candidate = candidate_entry.overlap_target_bbox
            if overlap_target_bbox_candidate is None:
                continue
            key = (
                str(candidate_entry.template_name),
                (
                    int(overlap_target_bbox_candidate[0]),
                    int(overlap_target_bbox_candidate[1]),
                    int(overlap_target_bbox_candidate[2]),
                    int(overlap_target_bbox_candidate[3]),
                ),
            )
            previous_best_entry = best_suppressed_nms_map.get(key)
            if previous_best_entry is None or float(candidate_entry.confidence) > float(previous_best_entry.confidence):
                best_suppressed_nms_map[key] = candidate_entry

        for debug_entry in template_debug_list:
            match_x, match_y, match_w, match_h = debug_entry.bbox
            window_x = int(match_x + region_x)
            window_y = int(match_y + region_y)
            window_w = int(match_w)
            window_h = int(match_h)

            confidence_percent = int(round(float(debug_entry.confidence) * 100.0))
            side_text = str(debug_entry.side or "")
            index_value = "" if debug_entry.index is None else str(debug_entry.index)
            base_label = f"{side_text}#{index_value}[{debug_entry.template_name}] {confidence_percent}%"

            is_suppressed = debug_entry.status != "kept"
            should_hide_overlay = _is_overlapped_same_template_suppressed_nms(
                debug_entry,
                template_debug_list,
            )

            hide_because_not_best_suppressed_nms = False
            if (
                is_suppressed
                and debug_entry.suppression_kind == "nms"
                and debug_entry.overlap_target_bbox is not None
            ):
                overlap_target_bbox_for_entry = debug_entry.overlap_target_bbox
                group_key = (
                    str(debug_entry.template_name),
                    (
                        int(overlap_target_bbox_for_entry[0]),
                        int(overlap_target_bbox_for_entry[1]),
                        int(overlap_target_bbox_for_entry[2]),
                        int(overlap_target_bbox_for_entry[3]),
                    ),
                )
                best_entry_for_group = best_suppressed_nms_map.get(group_key)
                if best_entry_for_group is not None and best_entry_for_group is not debug_entry:
                    hide_because_not_best_suppressed_nms = True

            if is_suppressed:
                suppression_reason_text = "未知规则"
                overlap_ratio_text = ""
                overlap_ratio_percent: int | None = None
                if debug_entry.suppression_kind == "nms":
                    overlap_ratio_value = debug_entry.iou
                    if isinstance(overlap_ratio_value, (int, float)):
                        overlap_ratio_clamped = float(overlap_ratio_value)
                        if overlap_ratio_clamped < 0.0:
                            overlap_ratio_clamped = 0.0
                        if overlap_ratio_clamped > 1.0:
                            overlap_ratio_clamped = 1.0
                        overlap_ratio_percent = int(round(overlap_ratio_clamped * 100.0))
                        overlap_ratio_text = f"，重叠率约 {overlap_ratio_percent}%"
                overlap_target_label_text = ""
                if debug_entry.suppression_kind == "nms":
                    suppression_reason_text = "NMS 重叠"
                    overlap_target_entry = _find_overlap_target_for_suppressed_nms(
                        debug_entry,
                        template_debug_list,
                    )
                    if overlap_target_entry is not None:
                        target_confidence_value = float(overlap_target_entry.confidence)
                        if target_confidence_value < 0.0:
                            target_confidence_value = 0.0
                        if target_confidence_value > 1.0:
                            target_confidence_value = 1.0
                        target_confidence_percent = int(round(target_confidence_value * 100.0))
                        target_side_text = str(overlap_target_entry.side or "")
                        target_index_value = "" if overlap_target_entry.index is None else str(overlap_target_entry.index)
                        target_base_label = (
                            f"{target_side_text}#{target_index_value}[{overlap_target_entry.template_name}] "
                            f"{target_confidence_percent}%"
                        )
                        overlap_target_label_text = f"，与 {target_base_label} 重叠"
                elif debug_entry.suppression_kind == "same_row":
                    suppression_reason_text = "同行去重"
                label = (
                    f"{base_label}（因{suppression_reason_text}"
                    f"{overlap_ratio_text}{overlap_target_label_text}被排除）"
                )
                color = (230, 90, 90)
                total_suppressed_matches += 1
                if len(suppressed_preview_snippets) < 3:
                    if overlap_ratio_percent is not None:
                        suppressed_preview_snippets.append(
                            f"{debug_entry.template_name} {confidence_percent}%（{suppression_reason_text}，重叠率约 {overlap_ratio_percent}%）"
                        )
                    else:
                        suppressed_preview_snippets.append(
                            f"{debug_entry.template_name} {confidence_percent}%（{suppression_reason_text}）"
                        )
            else:
                label = base_label
                color = (255, 160, 80) if side_text == "right" else (0, 200, 140)

            if not should_hide_overlay and not hide_because_not_best_suppressed_nms:
                rects.append(
                    {
                        "bbox": (window_x, window_y, window_w, window_h),
                        "color": color,
                        "label": label,
                    }
                )
            total_template_matches += 1

    overlays = {"rects": rects}
    self._update_visual(screenshot, overlays)
    if not nodes:
        self._log("✓ 深度端口识别测试完成：未检测到任何节点")
        return

    summary_message = (
        f"✓ 深度端口识别测试完成：检测节点 {len(nodes)} 个，"
        f"模板命中 {total_template_matches} 个（其中被排除 {total_suppressed_matches} 个，阈值≥70%）。"
    )
    self._log(summary_message)
    if total_suppressed_matches > 0 and suppressed_preview_snippets:
        extra_suffix = " 等" if total_suppressed_matches > len(suppressed_preview_snippets) else ""
        detail_message = f"· 被排除模板示例：{'；'.join(suppressed_preview_snippets)}{extra_suffix}"
        self._log(detail_message)


__all__ = ["test_ports_deep"]



