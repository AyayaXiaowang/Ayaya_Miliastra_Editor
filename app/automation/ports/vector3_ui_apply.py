# -*- coding: utf-8 -*-
"""
vector3_ui_apply: 三维向量输入的可视化与 UI 应用层。

职责：
- 负责三维向量各轴点击与文本注入的统一流程；
- 提供 OCR 区域与轴标签的可视化标注；
- 支持几何法点击位置的调试可视化。
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image

from app.automation.editor import executor_utils as _exec_utils


AxisLabel = str
BBox = Tuple[int, int, int, int]
Vector3ClickStep = Tuple[AxisLabel, int, int, str]


def visualize_ocr_region(
    executor,
    screenshot: Image.Image,
    search_region: Tuple[int, int, int, int],
    full_text: str,
    visual_callback,
) -> None:
    """高亮显示 OCR 搜索区域与摘要文本。"""
    if visual_callback is None:
        return

    search_left, search_top, search_width, search_height = search_region
    label_text = full_text if len(full_text) <= 80 else (full_text[:80] + "...")
    rects_region = [
        {
            "bbox": (search_left, search_top, search_width, search_height),
            "color": (255, 160, 0),
            "label": f"OCR: {label_text}",
        }
    ]
    executor.emit_visual(screenshot, {"rects": rects_region}, visual_callback)


def visualize_axis_bboxes(
    executor,
    screenshot: Image.Image,
    search_region: Tuple[int, int, int, int],
    label_to_bbox: Dict[AxisLabel, BBox],
    recognized_axes: Iterable[AxisLabel],
    visual_callback,
) -> None:
    """高亮显示识别与推断得到的各轴标签区域。"""
    if visual_callback is None or not label_to_bbox:
        return

    search_left, search_top, _search_width, _search_height = search_region
    recognized_set = {axis for axis in recognized_axes}

    rects_predicted: List[Dict[str, object]] = []
    for axis_label in ("X", "Y", "Z"):
        if axis_label not in label_to_bbox or axis_label in recognized_set:
            continue
        bbox_left, bbox_top, bbox_width, bbox_height = label_to_bbox[axis_label]
        rects_predicted.append(
            {
                "bbox": (search_left + bbox_left, search_top + bbox_top, bbox_width, bbox_height),
                "color": (120, 255, 120),
                "label": f"{axis_label}(推断)",
            }
        )

    if rects_predicted:
        executor.emit_visual(screenshot, {"rects": rects_predicted}, visual_callback)

    rects_all: List[Dict[str, object]] = []
    for axis_label, (bbox_left, bbox_top, bbox_width, bbox_height) in label_to_bbox.items():
        rects_all.append(
            {
                "bbox": (search_left + bbox_left, search_top + bbox_top, bbox_width, bbox_height),
                "color": (120, 200, 255),
                "label": f"{axis_label}",
            }
        )

    if rects_all:
        executor.emit_visual(screenshot, {"rects": rects_all}, visual_callback)


def visualize_geometry_click_candidates(
    executor,
    screenshot: Image.Image,
    click_plan: Iterable[Vector3ClickStep],
    visual_callback,
) -> None:
    """一次性展示几何法推导的三个轴点击位置。"""
    if visual_callback is None:
        return

    color_map: Dict[AxisLabel, Tuple[int, int, int]] = {
        "X": (0, 220, 0),
        "Y": (0, 200, 220),
        "Z": (220, 180, 0),
    }

    circles: List[Dict[str, object]] = []
    for axis_label, editor_x, editor_y, _ in click_plan:
        color = color_map.get(axis_label, (0, 220, 0))
        circles.append(
            {
                "center": (editor_x, editor_y),
                "radius": 5,
                "color": color,
                "label": axis_label,
            }
        )

    executor.emit_visual(screenshot, {"circles": circles}, visual_callback)


def _click_and_input_axis_value(
    executor,
    axis_label: AxisLabel,
    screen_x: int,
    screen_y: int,
    value_text: str,
    pause_hook,
    allow_continue,
    log_callback,
    *,
    click_label_suffix: str = "",
) -> bool:
    """在给定屏幕坐标点击并输入指定轴的数值。"""
    label_suffix_text = str(click_label_suffix or "")
    _exec_utils.click_and_verify(
        executor,
        screen_x,
        screen_y,
        f"[参数配置/三维向量] 点击{axis_label}{label_suffix_text}",
        log_callback,
    )

    executor.log(f"[参数配置/三维向量] 注入 {axis_label} 值: '{value_text}'", log_callback)
    if not executor.input_text_with_hooks(value_text, pause_hook, allow_continue, log_callback):
        return False

    _exec_utils.log_wait_if_needed(executor, 0.05, "等待 0.05 秒", log_callback)
    return True


def _visualize_and_click_axis(
    executor,
    screenshot: Image.Image,
    axis_label: AxisLabel,
    editor_x: int,
    editor_y: int,
    screen_x: int,
    screen_y: int,
    value_text: str,
    pause_hook,
    allow_continue,
    log_callback,
    visual_callback,
    *,
    click_label_suffix: str = "",
    highlight_bbox: Optional[BBox] = None,
) -> bool:
    """统一处理三维向量单轴点击的可视化与日志输出。"""
    if visual_callback is not None and highlight_bbox is not None:
        bbox_left, bbox_top, bbox_width, bbox_height = highlight_bbox
        rects_axis = [
            {
                "bbox": (bbox_left, bbox_top, bbox_width, bbox_height),
                "color": (120, 200, 255),
                "label": f"{axis_label}",
            }
        ]
        circles_axis = [
            {
                "center": (editor_x, editor_y),
                "radius": 5,
                "color": (0, 220, 0),
                "label": f"点击{axis_label}",
            }
        ]
        visual_callback(screenshot, {"rects": rects_axis, "circles": circles_axis})

    if click_label_suffix:
        executor.log(
            f"[参数配置/三维向量] {click_label_suffix} 点击 {axis_label}: "
            f"editor=({editor_x},{editor_y}) screen=({screen_x},{screen_y})",
            log_callback,
        )
    else:
        executor.log(
            f"[参数配置/三维向量] 点击 {axis_label} 输入框附近: "
            f"editor=({editor_x},{editor_y}) screen=({screen_x},{screen_y})",
            log_callback,
        )

    return _click_and_input_axis_value(
        executor,
        axis_label,
        screen_x,
        screen_y,
        value_text,
        pause_hook,
        allow_continue,
        log_callback,
        click_label_suffix=click_label_suffix,
    )


def apply_vector3_plan(
    executor,
    screenshot: Image.Image,
    click_plan: Iterable[Vector3ClickStep],
    pause_hook,
    allow_continue,
    log_callback,
    visual_callback,
    *,
    click_label_suffix: str = "",
    highlight_bboxes: Optional[Dict[AxisLabel, BBox]] = None,
    visualize_geometry_overview: bool = False,
) -> bool:
    """按照给定点击计划依次点击并输入三维向量各轴数值。"""
    plan_list = list(click_plan)

    if visualize_geometry_overview and plan_list:
        visualize_geometry_click_candidates(executor, screenshot, plan_list, visual_callback)

    for axis_label, editor_x, editor_y, value_text in plan_list:
        screen_x, screen_y = executor.convert_editor_to_screen_coords(editor_x, editor_y)
        highlight_bbox = None
        if highlight_bboxes is not None:
            highlight_bbox = highlight_bboxes.get(axis_label)

        ok = _visualize_and_click_axis(
            executor,
            screenshot,
            axis_label,
            editor_x,
            editor_y,
            screen_x,
            screen_y,
            value_text,
            pause_hook,
            allow_continue,
            log_callback,
            visual_callback,
            click_label_suffix=click_label_suffix,
            highlight_bbox=highlight_bbox,
        )
        if not ok:
            return False

    return True


