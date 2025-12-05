# -*- coding: utf-8 -*-
"""
执行器运行时常用钩子与交互工具：等待、文本输入、点击验证与模板匹配。

职责：
- 统一处理 pause_hook / allow_continue 的暂停与中断行为，并输出一致的日志；
- 提供带钩子的等待函数，支持在非快速链模式下分段 sleep 以响应全局控制；
- 封装右键点击前的画布吸附逻辑，以及左键点击后的光标偏移校验；
- 提供按水平行带的模板匹配工具，配合端口/配置步骤使用。
"""

from __future__ import annotations

from typing import Optional, Callable, Tuple
from pathlib import Path
from PIL import Image

from app.automation.core.executor_protocol import EditorExecutorProtocol
from app.automation import capture as editor_capture
from app.automation.input.common import sleep_seconds, DEFAULT_DRAG_MOUSE_UP_MS

from app.automation.core.executor_canvas_utils import snap_screen_point_to_canvas_background


def is_fast_chain_runtime_enabled(executor: EditorExecutorProtocol) -> bool:
    """判断当前步骤是否允许启用快速链模式。"""
    checker = getattr(executor, "is_fast_chain_step_enabled", None)
    if callable(checker):
        return bool(checker())
    return bool(getattr(executor, "fast_chain_mode", False))


def _run_with_pause_and_cancel(
    executor: EditorExecutorProtocol,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    cancel_log_message: str,
    log_callback: Optional[Callable[[str], None]],
) -> bool:
    """统一执行暂停/终止钩子，返回是否应继续执行当前操作。"""
    if pause_hook is not None:
        pause_hook()
    if allow_continue is not None and not allow_continue():
        executor.log(cancel_log_message, log_callback)
        return False
    return True


def wait_with_hooks(
    executor: EditorExecutorProtocol,
    total_seconds: float,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    interval_seconds: float = 0.1,
    log_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """在给定时长内以固定间隔轮询暂停/终止标志。False 表示应中止。"""
    executor.log(f"等待 {float(total_seconds):.2f} 秒...", log_callback)
    ticks = int(max(1, round(float(total_seconds) / float(interval_seconds))))
    for _ in range(int(ticks)):
        should_continue = _run_with_pause_and_cancel(
            executor,
            pause_hook,
            allow_continue,
            "用户终止/暂停，中止当前操作",
            log_callback,
        )
        if not should_continue:
            return False
        sleep_seconds(float(interval_seconds))
    return True


def input_text_with_hooks(
    executor: EditorExecutorProtocol,
    text: str,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    log_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    should_continue = _run_with_pause_and_cancel(
        executor,
        pause_hook,
        allow_continue,
        "用户终止/暂停，放弃输入文本",
        log_callback,
    )
    if not should_continue:
        return False
    ok = editor_capture.input_text(text)
    if not ok:
        executor.log("✗ 文本输入失败", log_callback)
        return False
    return True


def right_click_with_hooks(
    executor: EditorExecutorProtocol,
    screen_x: int,
    screen_y: int,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    log_callback: Optional[Callable[[str], None]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    *,
    linger_seconds: float = 0.0,
) -> bool:
    should_continue = _run_with_pause_and_cancel(
        executor,
        pause_hook,
        allow_continue,
        "用户终止/暂停，放弃右键点击",
        log_callback,
    )
    if not should_continue:
        return False
    snapped = snap_screen_point_to_canvas_background(
        executor,
        int(screen_x),
        int(screen_y),
        log_callback=log_callback,
        visual_callback=visual_callback,
    )
    if snapped is None:
        return False
    sx, sy = int(snapped[0]), int(snapped[1])
    post_release_override = float(linger_seconds) if float(linger_seconds) > 0 else None
    ok = editor_capture.click_right_button(
        int(sx),
        int(sy),
        post_release_sleep=post_release_override,
    )
    if not ok:
        executor.log("✗ 右键点击失败", log_callback)
        return False
    return True


def click_and_verify(
    executor: EditorExecutorProtocol,
    screen_x: int,
    screen_y: int,
    action_label: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """执行一次左键点击，并记录光标真实位置变化与目标偏差。"""
    before_x, before_y = editor_capture.get_cursor_pos()
    post_release_sleep = 0.0 if is_fast_chain_runtime_enabled(executor) else None
    editor_capture.click_left_button(
        int(screen_x),
        int(screen_y),
        post_release_sleep=post_release_sleep,
    )
    sleep_seconds(0.02)
    after_x, after_y = editor_capture.get_cursor_pos()
    delta_target_x = int(after_x - int(screen_x))
    delta_target_y = int(after_y - int(screen_y))
    delta_move_x = int(after_x - int(before_x))
    delta_move_y = int(after_y - int(before_y))
    executor.log(
        f"[鼠标] {action_label}: before=({int(before_x)},{int(before_y)}) -> after=({int(after_x)},{int(after_y)}) "
        f"target=({int(screen_x)},{int(screen_y)}) Δtarget=({delta_target_x},{delta_target_y}) Δmove=({delta_move_x},{delta_move_y})",
        log_callback,
    )


def log_wait_if_needed(
    executor: EditorExecutorProtocol,
    seconds: float,
    message: str,
    log_callback: Optional[Callable[[str], None]] = None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
) -> None:
    """在未启用快速链模式时记录等待日志并进行可选的带钩子等待。"""
    if float(seconds) <= 0:
        return
    if is_fast_chain_runtime_enabled(executor):
        return
    executor.log(message, log_callback)
    if pause_hook is None and allow_continue is None:
        sleep_seconds(float(seconds))
        return
    total = float(seconds)
    interval = min(0.1, total)
    ticks = int(max(1, round(total / interval)))
    for _ in range(int(ticks)):
        should_continue = _run_with_pause_and_cancel(
            executor,
            pause_hook,
            allow_continue,
            "用户终止/暂停，中止当前等待",
            log_callback,
        )
        if not should_continue:
            return
        sleep_seconds(float(interval))


def find_template_on_row(
    executor: EditorExecutorProtocol,
    screenshot: Image.Image,
    template_path: str,
    row_center_y: int,
    left_x: int,
    right_x: int,
    y_tolerance: int = 12,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Optional[Tuple[int, int, Tuple[int, int, int, int]]]:
    """在水平行带中匹配模板，返回 (center_x, center_y, bbox) 或 None。"""
    executor.log(
        f"[模板匹配] 水平带模板: '{Path(template_path).name}' 行中心y={int(row_center_y)} 容差±{int(y_tolerance)} 区间x=[{int(left_x)},{int(right_x)})",
        log_callback,
    )
    band_top = int(max(0, row_center_y - y_tolerance))
    band_bottom = int(row_center_y + y_tolerance)
    if band_bottom <= band_top:
        executor.log("  · 行带高度非法，放弃匹配", log_callback)
        return None
    if right_x <= left_x:
        executor.log("  · 水平范围非法，放弃匹配", log_callback)
        return None
    region = (int(left_x), int(band_top), int(right_x - left_x), int(band_bottom - band_top))
    match = editor_capture.match_template(screenshot, str(template_path), search_region=region)
    if not match:
        executor.log("  · 未命中模板", log_callback)
        return None
    mx, my, mw, mh, _ = match
    center_x = int(mx + mw // 2)
    center_y = int(my + mh // 2)
    executor.log(
        f"  ✓ 模板命中: bbox=({int(mx)},{int(my)},{int(mw)},{int(mh)}) center=({center_x},{center_y})",
        log_callback,
    )
    return (center_x, center_y, (int(mx), int(my), int(mw), int(mh)))



