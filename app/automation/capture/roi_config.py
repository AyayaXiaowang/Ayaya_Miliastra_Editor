# -*- coding: utf-8 -*-
"""
区域配置模块 (ROI - Region of Interest)
统一定义所有识别区域的配置和计算逻辑
"""

from typing import Tuple
from PIL import Image


# ============================================================
# 区域配置 - 统一定义所有识别区域
# ============================================================
REGIONS_CONFIG = {
    "顶部标签栏": {
        "enabled": True,
        "height_range": (0.03, 0.05),
        "width_range": (0.0, 1.0),
        "color": (255, 0, 0),
        "need_ocr": True,
        "ocr_method": "color_match",
        "target_color": "3E3E44",
        "color_tolerance": 20,
        "description": "当前标签名称"
    },
    "节点图目录": {
        "enabled": True,
        "height_range": (0.06, 0.73),
        "width_range": (0.0, 0.12),
        "color": (0, 255, 0),
        "need_ocr": False,
        "description": "节点图目录树"
    },
    "当前目录2": {
        "enabled": True,
        "height_range": (0.06, 0.094),
        "width_range": (0.125, 1.0),
        "color": (0, 0, 255),
        "need_ocr": False,
        "description": "当前目录路径"
    },
    "文件列表": {
        "enabled": True,
        "height_range": (0.095, 0.75),
        "width_range": (0.125, 1.0),
        "color": (255, 255, 0),
        "need_ocr": False,
        "description": "文件列表内容"
    },
    "节点图布置区域": {
        "enabled": True,
        "height_range": (0.095, 0.95),
        "width_range": (0.0, 1.0),
        "color": (255, 0, 255),
        "need_ocr": False,
        "description": "节点图编辑区"
    },
    "节点图底部菜单": {
        "enabled": True,
        "height_range": (0.95, 1.0),
        "width_range": (0.4, 0.6),
        "color": (0, 255, 255),
        "need_ocr": False,
        "description": "底部菜单栏"
    },
    # 基于"节点图布置区域"的派生区域：位于其底边正下方，水平居中，固定 70x70px
    "节点图缩放区域": {
        "enabled": True,
        "derived_from": "节点图布置区域",  # 基于该区域的锚点进行计算
        "anchor": "bottom_center",       # 取基准区域的底边中心作为锚点
        "size_px": (140, 70),             # 目标固定尺寸（像素）：宽140（左右各扩35），高70
        "offset_px": (0, 0),              # 以锚点为基准的偏移（x, y）
        "need_ocr": True,
        "description": "缩放百分比显示/输入框所在区域（期望识别数值如 50%）"
    }
}


def get_region_rect(screenshot: Image.Image, region_name: str) -> Tuple[int, int, int, int]:
    """根据区域名称和截图尺寸计算实际像素坐标
    
    Args:
        screenshot: PIL Image对象
        region_name: 区域名称
        
    Returns:
        (x, y, width, height) 像素坐标
    """
    if region_name not in REGIONS_CONFIG:
        raise ValueError(f"未定义的区域: {region_name}")
    
    config = REGIONS_CONFIG[region_name]
    img_width, img_height = screenshot.size

    # 支持"派生锚点区域"：基于另一个区域的锚点与固定像素尺寸
    if "derived_from" in config:
        base_name = str(config.get("derived_from"))
        base_x, base_y, base_w, base_h = get_region_rect(screenshot, base_name)
        anchor_mode = str(config.get("anchor", "bottom_center"))
        size_px = tuple(config.get("size_px", (0, 0)))
        offset_px = tuple(config.get("offset_px", (0, 0)))

        target_w = int(size_px[0])
        target_h = int(size_px[1])
        if str(region_name) == "节点图缩放区域":
            # 缩放区域像素大小受分辨率/Windows 缩放影响，统一走 profile 参数解析
            from app.automation.vision.ui_profile_params import get_zoom_region_size_px
            zoom_w, zoom_h = get_zoom_region_size_px()
            target_w = int(zoom_w)
            target_h = int(zoom_h)
        if target_w <= 0 or target_h <= 0:
            return (0, 0, 0, 0)

        if anchor_mode == "bottom_center":
            anchor_x = int(base_x + base_w // 2)
            anchor_y = int(base_y + base_h)
        else:
            # 默认退化为底边中心
            anchor_x = int(base_x + base_w // 2)
            anchor_y = int(base_y + base_h)

        out_x = int(anchor_x - target_w // 2 + int(offset_px[0]))
        out_y = int(anchor_y + int(offset_px[1]))

        # 约束在截图范围内（防止越界导致后续裁剪异常）
        out_x = max(0, min(int(out_x), int(img_width)))
        out_y = max(0, min(int(out_y), int(img_height)))
        # 宽高不做裁剪（允许越出窗口底边的定义，后续 OCR 会自然裁剪）
        return (int(out_x), int(out_y), int(target_w), int(target_h))

    # 常规比例区域
    height_start, height_end = config["height_range"]
    width_start, width_end = config["width_range"]
    
    x = int(img_width * width_start)
    y = int(img_height * height_start)
    width = int(img_width * (width_end - width_start))
    height = int(img_height * (height_end - height_start))
    
    return (x, y, width, height)


def get_region_center(screenshot: Image.Image, region_name: str) -> Tuple[int, int]:
    """获取区域的中心点坐标
    
    Args:
        screenshot: PIL Image对象
        region_name: 区域名称
        
    Returns:
        (center_x, center_y) 像素坐标
    """
    x, y, width, height = get_region_rect(screenshot, region_name)
    center_x = x + width // 2
    center_y = y + height // 2
    return (center_x, center_y)


def clip_to_graph_region(
    screenshot: Image.Image,
    rect: Tuple[int, int, int, int],
    graph_rect: Tuple[int, int, int, int] | None = None,
) -> Tuple[int, int, int, int]:
    """将给定矩形与"节点图布置区域"做求交裁剪，返回裁剪后的矩形 (x, y, w, h)。
    
    调用方负责根据业务决定是否在所有场景下都进行裁剪，或仅在强制阶段启用。
    
    Args:
        screenshot: PIL Image对象
        rect: 输入矩形 (x, y, width, height)
        graph_rect: 预先计算的节点图矩形（可选）
        
    Returns:
        裁剪后的矩形 (x, y, width, height)
    """
    input_left, input_top, input_width, input_height = int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])
    if graph_rect is None:
        region_left, region_top, region_width, region_height = get_region_rect(screenshot, "节点图布置区域")
    else:
        region_left, region_top, region_width, region_height = (
            int(graph_rect[0]),
            int(graph_rect[1]),
            int(graph_rect[2]),
            int(graph_rect[3]),
        )
    clip_left = max(int(input_left), int(region_left))
    clip_top = max(int(input_top), int(region_top))
    clip_right = min(int(input_left + input_width), int(region_left + region_width))
    clip_bottom = min(int(input_top + input_height), int(region_top + region_height))
    clipped_width = max(0, int(clip_right - clip_left))
    clipped_height = max(0, int(clip_bottom - clip_top))
    return (int(clip_left), int(clip_top), int(clipped_width), int(clipped_height))


def clip_to_image_bounds(
    screenshot: Image.Image,
    rect: Tuple[int, int, int, int],
) -> Tuple[int, int, int, int]:
    """将给定矩形裁剪到截图边界内，返回裁剪后的矩形 (x, y, w, h)。
    
    说明：
    - 用于处理弹窗/浮层等可能出现在节点图区域之外的 UI；
    - 仅做窗口边界裁剪，不依赖任何 ROI 策略开关。
    """
    input_left, input_top, input_width, input_height = int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])
    img_width, img_height = screenshot.size
    clip_left = max(0, int(input_left))
    clip_top = max(0, int(input_top))
    clip_right = min(int(input_left + input_width), int(img_width))
    clip_bottom = min(int(input_top + input_height), int(img_height))
    clipped_width = max(0, int(clip_right - clip_left))
    clipped_height = max(0, int(clip_bottom - clip_top))
    return (int(clip_left), int(clip_top), int(clipped_width), int(clipped_height))
