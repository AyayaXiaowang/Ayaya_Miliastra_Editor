# -*- coding: utf-8 -*-
"""
vector3_input_handler: 三维向量输入处理
从 config_params.py 提取的向量输入专用逻辑。
"""

from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, Callable, List
import re
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.core import executor_utils as _exec_utils
from app.automation.config.config_params_helpers import (
    parse_vector3_text,
    clip_to_node_bounds,
)
from app.automation.vision.ocr_utils import normalize_ocr_bbox


def match_axis_label_from_ocr(text_raw: str) -> Optional[str]:
    """从OCR文本中匹配轴标签（X/Y/Z）。
    
    允许常见噪声：冒号、全角冒号、等号、短横、字母O、数字0、中文"轴""值"等。
    
    Args:
        text_raw: OCR识别的原始文本
    
    Returns:
        轴标签 'X'/'Y'/'Z' 或 None
    """
    text = (text_raw or "").strip()
    if not text:
        return None
    
    text_upper = text.upper()
    text_normalized = text_upper.replace(" ", "")
    text_cleaned = text_normalized.replace(":", "").replace("：", "").replace("=", "").replace("-", "")
    
    # 精确匹配
    if text_cleaned in ("X", "Y", "Z"):
        return text_cleaned
    
    # 容错：YO/Z0/X0/XO 等（尾随 O/0）
    if re.match(r"^[XYZ][O0]$", text_cleaned):
        return text_cleaned[0]
    
    # 容错：尾随一个标点
    if re.match(r"^[XYZ][:：=\-]$", text_normalized):
        return text_normalized[0]
    
    # 容错：尾随中文"轴/值"
    if len(text_cleaned) == 2 and text_cleaned[0] in ("X", "Y", "Z") and text_cleaned[1] in ("轴", "值"):
        return text_cleaned[0]
    
    # 前缀匹配（最长3字符）：以 X/Y/Z 开头且其余仅包含允许字符
    if (len(text_cleaned) <= 3) and (text_cleaned[0] in ("X", "Y", "Z")):
        tail = text_cleaned[1:]
        if all(ch in ("O", "0") for ch in tail):
            return text_cleaned[0]
    
    return None


def build_axis_label_bbox_map(
    ocr_details: list,
    search_region: Tuple[int, int, int, int],
    log_callback=None,
    executor=None
) -> Dict[str, Tuple[int, int, int, int]]:
    """从OCR详细结果构建轴标签→相对bbox的映射（相对于搜索区域）。
    
    Args:
        ocr_details: OCR详细结果列表
        search_region: 搜索区域 (left, top, width, height)
        log_callback: 日志回调
        executor: 执行器实例（用于日志）
    
    Returns:
        {'X': (rel_left, rel_top, width, height), ...} 映射
    """
    label_to_bbox: Dict[str, Tuple[int, int, int, int]] = {}
    
    if not isinstance(ocr_details, list) or len(ocr_details) == 0:
        return label_to_bbox
    
    for item in ocr_details:
        if not isinstance(item, (list, tuple)):
            continue
        
        bbox_any = item[0] if len(item) > 0 else None
        text_item = str(item[1] if len(item) > 1 else "").strip()
        
        if not text_item:
            continue
        
        axis = match_axis_label_from_ocr(text_item)
        if axis is not None:
            label_left, label_top, label_width, label_height = normalize_ocr_bbox(bbox_any)
            if label_width > 0 and label_height > 0:
                label_to_bbox[axis] = (label_left, label_top, label_width, label_height)
    
    return label_to_bbox


def infer_missing_axis_positions(
    recognized_labels: Dict[str, Tuple[int, int, int, int]],
    search_region: Tuple[int, int, int, int]
) -> Dict[str, Tuple[int, int, int, int]]:
    """基于已识别的轴标签推断缺失轴的位置（等距推断）。
    
    仅当至少识别到两个轴时才进行推断。
    
    Args:
        recognized_labels: 已识别的轴标签bbox映射
        search_region: 搜索区域 (left, top, width, height)
    
    Returns:
        补全后的轴标签bbox映射
    """
    result = dict(recognized_labels)
    
    recognized_axes = [k for k in ("X", "Y", "Z") if k in result]
    if len(recognized_axes) < 2:
        return result
    
    # 计算平均尺寸与中心Y
    widths = [int(result[k][2]) for k in recognized_axes]
    heights = [int(result[k][3]) for k in recognized_axes]
    avg_width = int(sum(widths) / len(widths)) if len(widths) > 0 else 12
    avg_height = int(sum(heights) / len(heights)) if len(heights) > 0 else 12
    
    centers = {k: (int(result[k][0] + result[k][2] // 2), int(result[k][1] + result[k][3] // 2)) for k in recognized_axes}
    avg_center_y = int(sum([c[1] for c in centers.values()]) / len(centers))
    
    region_width = int(search_region[2])
    region_height = int(search_region[3])
    
    def clip_value(val: int, lo: int, hi: int) -> int:
        return lo if val < lo else (hi if val > hi else val)
    
    def infer_center_x(missing_axis: str) -> int:
        if missing_axis == "X" and ("Y" in centers and "Z" in centers):
            spacing = int(centers["Z"][0] - centers["Y"][0])
            return int(centers["Y"][0] - spacing)
        if missing_axis == "Z" and ("X" in centers and "Y" in centers):
            spacing = int(centers["Y"][0] - centers["X"][0])
            return int(centers["Y"][0] + spacing)
        if missing_axis == "Y" and ("X" in centers and "Z" in centers):
            return int((centers["X"][0] + centers["Z"][0]) / 2)
        return centers.get("Y", (0, 0))[0]
    
    for missing_axis in ("X", "Y", "Z"):
        if missing_axis not in result and len(recognized_axes) >= 2:
            center_x = infer_center_x(missing_axis)
            center_x = clip_value(center_x, avg_width // 2, region_width - avg_width // 2)
            center_y = clip_value(avg_center_y, avg_height // 2, region_height - avg_height // 2)
            
            rel_left = int(center_x - avg_width // 2)
            rel_top = int(center_y - avg_height // 2)
            result[missing_axis] = (rel_left, rel_top, avg_width, avg_height)
    
    return result


def _click_and_input_axis_value(
    executor,
    axis_label: str,
    screen_x: int,
    screen_y: int,
    value_text: str,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
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

    executor._log(f"[参数配置/三维向量] 注入 {axis_label} 值: '{value_text}'", log_callback)
    if not executor._input_text_with_hooks(value_text, pause_hook, allow_continue, log_callback):
        return False

    _exec_utils.log_wait_if_needed(executor, 0.05, "等待 0.05 秒", log_callback)
    return True


def _visualize_and_click_axis(
    executor,
    screenshot: Image.Image,
    axis_label: str,
    editor_x: int,
    editor_y: int,
    screen_x: int,
    screen_y: int,
    value_text: str,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    log_callback,
    visual_callback,
    *,
    click_label_suffix: str = "",
    highlight_bbox: Optional[Tuple[int, int, int, int]] = None,
) -> bool:
    """统一处理三维向量单轴点击的可视化与日志输出."""
    if visual_callback is not None and highlight_bbox is not None:
        bbox_left, bbox_top, bbox_w, bbox_h = highlight_bbox
        rects_axis = [
            {
                "bbox": (bbox_left, bbox_top, bbox_w, bbox_h),
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
        executor._log(
            f"[参数配置/三维向量] {click_label_suffix} 点击 {axis_label}: editor=({editor_x},{editor_y}) screen=({screen_x},{screen_y})",
            log_callback,
        )
    else:
        executor._log(
            f"[参数配置/三维向量] 点击 {axis_label} 输入框附近: editor=({editor_x},{editor_y}) screen=({screen_x},{screen_y})",
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


def input_vector3_by_ocr(
    executor,
    screenshot: Image.Image,
    search_region: Tuple[int, int, int, int],
    node_bbox: Tuple[int, int, int, int],
    param_value: str,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    log_callback,
    visual_callback
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
    search_left, search_top, search_width, search_height = search_region
    
    # OCR识别
    full_text, details = editor_capture.ocr_recognize_region(screenshot, search_region, return_details=True)
    executor._log(f"[参数配置/三维向量] OCR文本: '{full_text}'", log_callback)
    
    # 可视化：OCR区域
    if visual_callback is not None:
        label_text = full_text if len(full_text) <= 80 else (full_text[:80] + "...")
        rects_region = [{
            'bbox': (search_left, search_top, search_width, search_height),
            'color': (255, 160, 0),
            'label': f"OCR: {label_text}"
        }]
        executor._emit_visual(screenshot, {'rects': rects_region}, visual_callback)
    
    # 构建标签bbox映射
    label_to_bbox = build_axis_label_bbox_map(details, search_region, log_callback, executor)
    recognized_axes = set(label_to_bbox.keys())
    
    # 推断缺失轴
    label_to_bbox = infer_missing_axis_positions(label_to_bbox, search_region)
    
    # 可视化：推断出的轴
    if visual_callback is not None:
        rects_pred = []
        for axis_key in ("X", "Y", "Z"):
            if axis_key in label_to_bbox and axis_key not in recognized_axes:
                bbox_x, bbox_y, bbox_w, bbox_h = label_to_bbox[axis_key]
                rects_pred.append({
                    'bbox': (search_left + bbox_x, search_top + bbox_y, bbox_w, bbox_h),
                    'color': (120, 255, 120),
                    'label': f"{axis_key}(推断)"
                })
        if len(rects_pred) > 0:
            executor._emit_visual(screenshot, {'rects': rects_pred}, visual_callback)
    
    # 可视化：所有轴标签
    if visual_callback is not None and len(label_to_bbox) > 0:
        rects_all = []
        for axis_key, (bbox_x, bbox_y, bbox_w, bbox_h) in label_to_bbox.items():
            rects_all.append({
                'bbox': (search_left + bbox_x, search_top + bbox_y, bbox_w, bbox_h),
                'color': (120, 200, 255),
                'label': f"{axis_key}"
            })
        executor._emit_visual(screenshot, {'rects': rects_all}, visual_callback)
    
    # 日志：标签命中摘要
    hit_x = 'X' in label_to_bbox
    hit_y = 'Y' in label_to_bbox
    hit_z = 'Z' in label_to_bbox
    executor._log(f"[参数配置/三维向量] 标签命中: X={hit_x} Y={hit_y} Z={hit_z}", log_callback)
    
    # 解析向量值
    x_val, y_val, z_val = parse_vector3_text(param_value)
    plan: List[Tuple[str, str]] = [("X", x_val), ("Y", y_val), ("Z", z_val)]
    
    # 依次点击并输入各轴
    for axis_label, axis_value in plan:
        bbox = label_to_bbox.get(axis_label)
        if bbox is None:
            executor._log(f"[参数配置/三维向量] 未识别到标签 '{axis_label}'，放弃按轴输入", log_callback)
            return False

        bbox_x, bbox_y, bbox_w, bbox_h = bbox

        # 点击标签中心略向右12px以进入对应输入框
        click_editor_x = search_left + bbox_x + max(1, bbox_w) // 2 + 12
        click_editor_y = search_top + bbox_y + max(1, bbox_h) // 2

        # 裁剪到节点范围
        click_editor_x, click_editor_y = clip_to_node_bounds(click_editor_x, click_editor_y, node_bbox)

        screen_x, screen_y = executor.convert_editor_to_screen_coords(click_editor_x, click_editor_y)

        if not _visualize_and_click_axis(
            executor,
            screenshot,
            axis_label,
            click_editor_x,
            click_editor_y,
            screen_x,
            screen_y,
            axis_value,
            pause_hook,
            allow_continue,
            log_callback,
            visual_callback,
            click_label_suffix="",
            highlight_bbox=(search_left + bbox_x, search_top + bbox_y, bbox_w, bbox_h),
        ):
            return False
    
    return True


def input_vector3_by_geometry(
    executor,
    screenshot: Image.Image,
    warning_bbox: Tuple[int, int, int, int, float],
    node_bbox: Tuple[int, int, int, int],
    current_port_bbox: Tuple[int, int, int, int],
    param_value: str,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    log_callback,
    visual_callback
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
    warning_x, warning_y, warning_w, warning_h, _conf = warning_bbox
    
    # Z：使用Warning模板的左下角作为中心点
    z_center_x = int(warning_x)
    z_center_y = int(warning_y + warning_h)
    
    # 端口几何信息
    port_right_edge = int(current_port_bbox[0] + current_port_bbox[2])
    port_width = int(current_port_bbox[2]) if int(current_port_bbox[2]) > 0 else 60
    
    # X：从端口右侧边向右延伸一个端口宽度
    x_center_x = int(port_right_edge + port_width)
    x_center_y = int(z_center_y)
    
    # Y：X与Z的中点
    y_center_x = int((x_center_x + z_center_x) / 2)
    y_center_y = int(z_center_y)
    
    # 裁剪到节点bbox内部
    x_center_x, x_center_y = clip_to_node_bounds(x_center_x, x_center_y, node_bbox)
    y_center_x, y_center_y = clip_to_node_bounds(y_center_x, y_center_y, node_bbox)
    z_center_x, z_center_y = clip_to_node_bounds(z_center_x, z_center_y, node_bbox)
    
    # 解析向量值
    x_val, y_val, z_val = parse_vector3_text(param_value)
    plan_xyz = [
        ("X", x_center_x, x_center_y, x_val),
        ("Y", y_center_x, y_center_y, y_val),
        ("Z", z_center_x, z_center_y, z_val),
    ]
    
    # 可视化：三个点击位置
    if visual_callback is not None:
        circles_xyz = [
            {'center': (x_center_x, x_center_y), 'radius': 5, 'color': (0, 220, 0), 'label': 'X'},
            {'center': (y_center_x, y_center_y), 'radius': 5, 'color': (0, 200, 220), 'label': 'Y'},
            {'center': (z_center_x, z_center_y), 'radius': 5, 'color': (220, 180, 0), 'label': 'Z'},
        ]
        executor._emit_visual(screenshot, {'circles': circles_xyz}, visual_callback)
    
    # 依次点击并输入各轴
    for axis_label, center_x, center_y, value_text in plan_xyz:
        screen_x, screen_y = executor.convert_editor_to_screen_coords(center_x, center_y)

        if not _visualize_and_click_axis(
            executor,
            screenshot,
            axis_label,
            center_x,
            center_y,
            screen_x,
            screen_y,
            value_text,
            pause_hook,
            allow_continue,
            log_callback,
            visual_callback,
            click_label_suffix="(几何)",
            highlight_bbox=None,
        ):
            return False
    
    return True

