from __future__ import annotations

from typing import Callable, Optional, Tuple

import numpy as np
from PIL import Image


ScreenPoint = Tuple[int, int]


def mean_abs_diff_in_region(
    image_a: Image.Image,
    image_b: Image.Image,
    center: ScreenPoint,
    half: int = 30,
) -> float:
    """计算指定中心附近区域的平均像素差值。"""
    cx, cy = int(center[0]), int(center[1])
    radius = int(half)
    left = max(0, cx - radius)
    top = max(0, cy - radius)
    right = min(cx + radius, image_a.width)
    bottom = min(cy + radius, image_a.height)
    if left >= right or top >= bottom:
        return 0.0
    crop_a = image_a.crop((left, top, right, bottom))
    crop_b = image_b.crop((left, top, right, bottom))
    arr_a = np.asarray(crop_a, dtype=np.int16)
    arr_b = np.asarray(crop_b, dtype=np.int16)
    if arr_a.shape != arr_b.shape or arr_a.size == 0:
        return 0.0
    diff = np.abs(arr_a - arr_b)
    return float(diff.mean())


def perform_connection_drag(
    *,
    drag_callable: Callable[[int, int, int, int], None],
    src_screen: ScreenPoint,
    dst_screen: ScreenPoint,
    log_fn: Callable[[str], None],
    description: str,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    verify_callable: Optional[Callable[[], bool]] = None,
) -> bool:
    """执行端口连线拖拽，统一处理暂停/终止与可选验证。"""
    log_fn(f"拖拽连线: {description}")
    if pause_hook is not None:
        pause_hook()
    if allow_continue is not None and not allow_continue():
        log_fn("用户终止/暂停，放弃拖拽连线")
        return False
    drag_callable(
        int(src_screen[0]),
        int(src_screen[1]),
        int(dst_screen[0]),
        int(dst_screen[1]),
    )
    if verify_callable is None:
        return True
    return bool(verify_callable())

