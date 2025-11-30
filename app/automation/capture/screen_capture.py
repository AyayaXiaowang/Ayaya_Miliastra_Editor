# -*- coding: utf-8 -*-
"""
截图模块
负责窗口和屏幕的图像捕获
"""

import ctypes
from typing import Optional, Tuple
from PIL import ImageGrab, Image

from .roi_config import get_region_rect
from .dpi_awareness import ensure_dpi_awareness_once
from app.automation.input.window_finder import find_window_handle
from app.automation.input.win_input import get_client_rect


def get_window_rect(window_title: str) -> Optional[Tuple[int, int, int, int]]:
    """获取指定标题的窗口位置和尺寸
    
    Args:
        window_title: 窗口标题
        
    Returns:
        (left, top, right, bottom) 或 None（未找到窗口时）
    """
    class RECT(ctypes.Structure):
        _fields_ = [
            ('left', ctypes.c_long),
            ('top', ctypes.c_long),
            ('right', ctypes.c_long),
            ('bottom', ctypes.c_long)
        ]
    
    hwnd = find_window_handle(window_title, case_sensitive=False)
    
    if hwnd == 0:
        return None
    
    rect = RECT()
    result = ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    
    if result == 0:
        return None
    
    return rect.left, rect.top, rect.right, rect.bottom


def capture_client_image(hwnd: int) -> Image.Image:
    """截取指定窗口客户区图像（支持多显示器）
    
    Args:
        hwnd: 窗口句柄
        
    Returns:
        PIL Image对象
    """
    ensure_dpi_awareness_once()
    rect = get_client_rect(hwnd)
    left = int(rect.left)
    top = int(rect.top)
    right = int(rect.right)
    bottom = int(rect.bottom)
    screenshot = ImageGrab.grab(bbox=(int(left), int(top), int(right), int(bottom)), all_screens=True)
    return screenshot


def capture_window(window_title: str) -> Optional[Image.Image]:
    """截取指定窗口的图像
    
    Args:
        window_title: 窗口标题
        
    Returns:
        PIL Image对象，未找到窗口时返回 None
    """
    ensure_dpi_awareness_once()
    window_rect = get_window_rect(window_title)
    
    if window_rect is None:
        return None
    
    left, top, right, bottom = window_rect
    screenshot = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    
    return screenshot


def capture_full_screen() -> Image.Image:
    """截取整个屏幕
    
    Returns:
        PIL Image对象
    """
    ensure_dpi_awareness_once()
    screenshot = ImageGrab.grab(all_screens=True)
    return screenshot


def capture_screen_region(region: Tuple[int, int, int, int]) -> Image.Image:
    """截取指定的屏幕绝对坐标区域。"""
    left, top, width, height = region
    if int(width) <= 0 or int(height) <= 0:
        raise ValueError("region width/height must be positive")
    bbox = (int(left), int(top), int(left + width), int(top + height))
    ensure_dpi_awareness_once()
    return ImageGrab.grab(bbox=bbox, all_screens=True)


def get_region_image(screenshot: Image.Image, region_name: str) -> Image.Image:
    """返回指定命名区域的裁剪图像
    
    Args:
        screenshot: PIL Image对象
        region_name: 区域名称
        
    Returns:
        裁剪后的 PIL Image对象
    """
    x, y, w, h = get_region_rect(screenshot, region_name)
    return screenshot.crop((x, y, x + w, y + h))


def capture_region(window_title: str, region_name: str) -> Optional[Image.Image]:
    """截取窗口并返回指定命名区域图像
    
    Args:
        window_title: 窗口标题
        region_name: 区域名称
        
    Returns:
        裁剪后的 PIL Image对象，未找到窗口返回 None
    """
    window_image = capture_window(window_title)
    if window_image is None:
        return None
    return get_region_image(window_image, region_name)

