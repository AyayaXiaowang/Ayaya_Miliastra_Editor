# -*- coding: utf-8 -*-
"""
颜色扫描模块
负责在截图中查找特定颜色的区域
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional
from PIL import Image


def prepare_color_scan_image(screenshot: Image.Image):
    """将截图转换为 BGR numpy 数组，供颜色扫描复用。"""
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)


def find_color_rectangles(
    screenshot: Image.Image,
    target_color_hex: str = "26262C",
    color_tolerance: int = 20,
    near_point: Optional[Tuple[int, int]] = None,
    max_distance: int = 500,
    *,
    prepared_bgr = None
) -> List[Tuple[int, int, int, int, float]]:
    """在整个截图中查找特定颜色的矩形区域
    
    Args:
        screenshot: PIL Image对象
        target_color_hex: 目标颜色的十六进制字符串（不含#）
        color_tolerance: 颜色容差
        near_point: 可选的参考点坐标 (x, y)，用于筛选附近的矩形
        max_distance: 当指定 near_point 时，最大距离阈值
        
    Returns:
        矩形列表 [(x, y, width, height, distance), ...]，按距离排序
    """
    if prepared_bgr is not None:
        img_bgr = prepared_bgr
    else:
        img_bgr = prepare_color_scan_image(screenshot)
    
    target_r = int(target_color_hex[0:2], 16)
    target_g = int(target_color_hex[2:4], 16)
    target_b = int(target_color_hex[4:6], 16)
    target_color_bgr = np.array([target_b, target_g, target_r], dtype=np.uint8)
    
    lower_bound = np.clip(target_color_bgr - color_tolerance, 0, 255)
    upper_bound = np.clip(target_color_bgr + color_tolerance, 0, 255)
    
    mask = cv2.inRange(img_bgr, lower_bound, upper_bound)
    
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    rectangles = []
    screen_width, screen_height = screenshot.size
    
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)

        min_width = 50
        min_height = 30
        if w < min_width or h < min_height:
            continue

        if w >= screen_width * 0.95 and h >= screen_height * 0.95:
            continue

        # 计算点击点到矩形的最短距离（在矩形内部则为0）
        if near_point is not None:
            px, py = int(near_point[0]), int(near_point[1])
            # 判断是否在矩形内部
            inside = (px >= int(x) and px <= int(x + w) and py >= int(y) and py <= int(y + h))
            if inside:
                dist = 0.0
            else:
                dx = 0
                if px < int(x):
                    dx = int(x) - px
                elif px > int(x + w):
                    dx = px - int(x + w)
                dy = 0
                if py < int(y):
                    dy = int(y) - py
                elif py > int(y + h):
                    dy = py - int(y + h)
                dist = float((dx * dx + dy * dy) ** 0.5)
            if dist <= float(max_distance):
                rectangles.append((int(x), int(y), int(w), int(h), float(dist)))
        else:
            center_x = int(x + w // 2)
            center_y = int(y + h // 2)
            rectangles.append((int(x), int(y), int(w), int(h), 0.0))
    
    rectangles.sort(key=lambda r: r[4])
    
    return rectangles

