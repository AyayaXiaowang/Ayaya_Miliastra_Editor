from __future__ import annotations

from typing import Callable, Generator, Iterable, List, Optional, Tuple

from PIL import Image

from app.automation.vision import phase_correlation_delta


def estimate_content_motion(
    before_image: Image.Image,
    after_image: Image.Image,
    roi: Optional[Tuple[int, int, int, int]] = None,
) -> Tuple[int, int]:
    """在可选 ROI 内估计内容位移（像素，窗口/客户区坐标系）。

    - 无 ROI：对整幅图执行相位相关
    - 有 ROI：在裁剪区域执行相位相关
    返回 (dx, dy)
    """
    if roi is None:
        dx, dy = phase_correlation_delta(before_image, after_image)
        return int(dx), int(dy)

    rx, ry, rw, rh = roi
    before_crop = before_image.crop((rx, ry, rx + rw, ry + rh))
    after_crop = after_image.crop((rx, ry, rx + rw, ry + rh))
    dx, dy = phase_correlation_delta(before_crop, after_crop)
    return int(dx), int(dy)


def perform_drag_with_motion_estimation(
    before_image: Image.Image,
    *,
    drag_action: Callable[[], None],
    capture_after: Callable[[], Image.Image | None],
    roi: Optional[Tuple[int, int, int, int]] = None,
) -> Tuple[Image.Image, int, int]:
    """执行一次拖拽动作并基于相位相关估计内容位移。"""
    drag_action()
    after_image = capture_after()
    if after_image is None:
        raise ValueError("拖拽后截图失败")
    dx, dy = estimate_content_motion(before_image, after_image, roi)
    return after_image, int(dx), int(dy)


def compute_segmented_pan_unit(vector_x: int, vector_y: int, max_step_pixels: int) -> Tuple[int, int, int]:
    """按照“分段裁剪”的策略，计算单步单位位移与步数。

    返回 (unit_x, unit_y, step_count)，调用方可循环 step_count 次执行 pan。
    逻辑与 `RealExecutor.ensure_visible_node` 中保持一致以避免行为变化。
    """
    length = max(1, int((vector_x ** 2 + vector_y ** 2) ** 0.5))
    if length == 0:
        length = 1
    step_count = max(1, min(max_step_pixels, length) // max_step_pixels)
    denom = max(1, step_count)
    unit_x = int(vector_x / denom)
    unit_y = int(vector_y / denom)
    return unit_x, unit_y, step_count


def compute_clamped_step(vector_x: int, vector_y: int, max_step_pixels: int) -> Tuple[int, int]:
    """将单步拖拽限制在最大像素内（编辑器执行器使用）。"""
    step_x = max(-max_step_pixels, min(max_step_pixels, int(vector_x)))
    step_y = max(-max_step_pixels, min(max_step_pixels, int(vector_y)))
    return step_x, step_y


def compute_safe_rect(region_x: int, region_y: int, region_w: int, region_h: int, margin_ratio: float) -> Tuple[int, int, int, int]:
    """计算“视口安全区”矩形：在区域四周各收缩 margin_ratio。

    返回 (x, y, w, h)（均为整数）。
    """
    shrink_x = int(region_w * margin_ratio)
    shrink_y = int(region_h * margin_ratio)
    x = int(region_x + shrink_x)
    y = int(region_y + shrink_y)
    w = int(region_w - shrink_x * 2)
    h = int(region_h - shrink_y * 2)
    if w < 1:
        w = 1
    if h < 1:
        h = 1
    return x, y, w, h


def is_point_in_rect(px: int, py: int, rect: Tuple[int, int, int, int]) -> bool:
    rx, ry, rw, rh = rect
    return (px >= rx) and (py >= ry) and (px < rx + rw) and (py < ry + rh)


def generate_spiral_deltas(step: int = 360, rings: int = 6) -> Iterable[Tuple[int, int]]:
    """生成螺旋搜索的位移序列（以内容移动方向表示的 pan 向量）。

    模式：→ step, ↓ step, ← 2step, ↑ 2step, → 3step, ...
    返回 (dx, dy) 的迭代器。
    """
    delta_sequence = [(step, 0), (0, step), (-step, 0), (0, -step)]
    length_multiplier = 1
    for _ring in range(1, rings + 1):
        for direction_index, (dx_unit, dy_unit) in enumerate(delta_sequence):
            repeat = 1 if direction_index < 2 else 2
            for _ in range(repeat * length_multiplier):
                yield dx_unit, dy_unit
        length_multiplier += 1


