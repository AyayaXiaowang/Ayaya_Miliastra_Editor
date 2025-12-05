# -*- coding: utf-8 -*-
"""
vector3_input_handler: 三维向量输入处理
从 config_params.py 提取的向量输入专用逻辑。
"""

from __future__ import annotations

from typing import Optional, Tuple, Callable
from PIL import Image

from app.automation.core.executor_protocol import AutomationStepContext

from app.automation import capture as editor_capture
from app.automation.config.config_params_helpers import (
    parse_vector3_text,
)
from app.automation.ports.vector3_axis_detection import (
    build_axis_label_bbox_map,
    infer_missing_axis_positions,
)
from app.automation.ports.vector3_click_strategy import (
    build_geometry_click_plan_for_vector3,
    build_ocr_click_plan_for_vector3,
)
from app.automation.ports.vector3_ui_apply import (
    apply_vector3_plan,
    visualize_axis_bboxes,
    visualize_ocr_region,
)


def input_vector3_by_ocr(
    executor,
    screenshot: Image.Image,
    search_region: Tuple[int, int, int, int],
    node_bbox: Tuple[int, int, int, int],
    param_value: str,
    ctx: AutomationStepContext,
) -> bool:
    """通过OCR识别X/Y/Z标签位置并分别输入向量分量。
    
    Args:
        executor: 执行器实例
        screenshot: 当前截图
        search_region: OCR搜索区域 (left, top, width, height)
        node_bbox: 节点边界框
        param_value: 向量文本值
        pause_hook: 暂停钩子
        allow_continue: 继续判断钩子
        log_callback: 日志回调
        visual_callback: 可视化回调
    
    Returns:
        成功返回True，失败返回False
    """
    log_callback = ctx.log_callback
    visual_callback = ctx.visual_callback

    # OCR识别
    full_text, ocr_details = editor_capture.ocr_recognize_region(
        screenshot,
        search_region,
        return_details=True,
    )
    executor.log(f"[参数配置/三维向量] OCR文本: '{full_text}'", log_callback)

    # 可视化：OCR 区域
    visualize_ocr_region(executor, screenshot, search_region, full_text, visual_callback)

    # 构建标签 bbox 映射并推断缺失轴
    label_to_bbox_raw = build_axis_label_bbox_map(ocr_details)
    recognized_axes = set(label_to_bbox_raw.keys())
    label_to_bbox = infer_missing_axis_positions(label_to_bbox_raw, search_region)

    # 可视化：轴标签与推断结果
    visualize_axis_bboxes(
        executor,
        screenshot,
        search_region,
        label_to_bbox,
        recognized_axes,
        visual_callback,
    )
    
    # 日志：标签命中摘要
    hit_x = "X" in label_to_bbox
    hit_y = "Y" in label_to_bbox
    hit_z = "Z" in label_to_bbox
    executor.log(f"[参数配置/三维向量] 标签命中: X={hit_x} Y={hit_y} Z={hit_z}", log_callback)
    
    # 解析向量值
    # 若任意轴缺失，则直接放弃本次三维向量输入
    for axis_label in ("X", "Y", "Z"):
        if axis_label not in label_to_bbox:
            executor.log(
                f"[参数配置/三维向量] 未识别到标签 '{axis_label}'，放弃按轴输入",
                log_callback,
            )
            return False

    # 解析向量值
    x_value, y_value, z_value = parse_vector3_text(param_value)

    # 规划点击计划与高亮区域
    click_plan, highlight_bboxes = build_ocr_click_plan_for_vector3(
        label_to_bbox,
        search_region,
        node_bbox,
        x_value,
        y_value,
        z_value,
    )

    # 统一执行点击与文本注入
    return apply_vector3_plan(
        executor,
        screenshot,
        click_plan,
        ctx.pause_hook,
        ctx.allow_continue,
        ctx.log_callback,
        ctx.visual_callback,
        click_label_suffix="(OCR)",
        highlight_bboxes=highlight_bboxes,
        visualize_geometry_overview=False,
    )


def input_vector3_by_geometry(
    executor,
    screenshot: Image.Image,
    warning_bbox: Tuple[int, int, int, int, float],
    node_bbox: Tuple[int, int, int, int],
    current_port_bbox: Tuple[int, int, int, int],
    param_value: str,
    ctx: AutomationStepContext,
) -> bool:
    """基于Warning模板几何位置定位X/Y/Z输入框并输入向量分量。
    
    使用几何法：
    - Z：Warning模板左下角
    - X：端口右侧边向右延伸一个端口宽度
    - Y：X与Z的中点
    - 三者共线（同一水平高度）
    
    Args:
        executor: 执行器实例
        screenshot: 当前截图
        warning_bbox: Warning模板命中框 (x, y, w, h, conf)
        node_bbox: 节点边界框
        current_port_bbox: 当前端口边界框
        param_value: 向量文本值
        pause_hook: 暂停钩子
        allow_continue: 继续判断钩子
        log_callback: 日志回调
        visual_callback: 可视化回调
    
    Returns:
        成功返回True，失败返回False
    """
    # 解析向量值
    x_value, y_value, z_value = parse_vector3_text(param_value)

    # 基于几何信息规划点击计划
    click_plan = build_geometry_click_plan_for_vector3(
        warning_bbox,
        node_bbox,
        current_port_bbox,
        x_value,
        y_value,
        z_value,
    )

    # 可视化与执行点击
    return apply_vector3_plan(
        executor,
        screenshot,
        click_plan,
        ctx.pause_hook,
        ctx.allow_continue,
        ctx.log_callback,
        ctx.visual_callback,
        click_label_suffix="(几何)",
        highlight_bboxes=None,
        visualize_geometry_overview=True,
    )

