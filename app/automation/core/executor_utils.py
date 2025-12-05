# -*- coding: utf-8 -*-
"""
EditorExecutor 的通用工具函数门面模块：等待钩子、文本输入、点击校验、模板行匹配与画布吸附。

设计说明：
- 实际实现按职责拆分到 `executor_canvas_utils.py` 与 `executor_hook_utils.py` 中；
- 对外仍通过本模块暴露统一的函数入口，保持现有调用方 `from app.automation.core import executor_utils`
  的导入方式不变；
- 不做异常吞噬；调用方按既有逻辑抛错或返回。
"""

from __future__ import annotations

from typing import Optional, Callable, Tuple
from pathlib import Path
from PIL import Image

from app.automation.core.executor_protocol import EditorExecutorProtocol

from app.automation.core.executor_canvas_utils import (
    CANVAS_ALLOWED_COLORS,
    CANVAS_COLOR_TOLERANCES,
    CANVAS_COLOR_MAX_DISTANCES,
    CANVAS_FALLBACK_GRID_STEPS_X,
    CANVAS_FALLBACK_GRID_STEPS_Y,
    CANVAS_SAFE_POINT_NEAR_MAX_RADIUS,
    CANVAS_SAFE_POINT_NEAR_STEP,
    CANVAS_RECT_SAMPLE_STEPS_X,
    CANVAS_RECT_SAMPLE_STEPS_Y,
    snap_screen_point_to_canvas_background,
)

from app.automation.core.executor_hook_utils import (
    is_fast_chain_runtime_enabled,
    wait_with_hooks,
    input_text_with_hooks,
    right_click_with_hooks,
    click_and_verify,
    log_wait_if_needed,
    find_template_on_row,
)


def make_executor_log_fn(
    executor: EditorExecutorProtocol,
    log_callback: Optional[Callable[[str], None]] = None,
    ) -> Callable[[str], None]:
    """基于执行器与可选日志回调构造统一的日志函数。
    
    返回的函数签名为 ``log(message: str) -> None``，内部统一调用
    ``executor.log(message, log_callback)``，便于在调用点通过闭包简化
    日志书写，同时保持前缀与回调策略一致。
    """
    
    def log(message: str) -> None:
        executor.log(message, log_callback)
    
    return log


def click_canvas_blank_near_screen_point(
    executor: EditorExecutorProtocol,
    start_screen_x: int,
    start_screen_y: int,
    *,
    log_prefix: str,
    wait_seconds: float = 0.1,
    wait_message: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
) -> bool:
    """
    基于当前屏幕坐标在画布区域内寻找安全空白点并点击，常用于
    “关闭对话框/收起弹窗后让节点图恢复稳定状态”这一类收尾步骤。

    返回:
        - True: 已成功点击空白点并完成等待；
        - False: 未能找到画布空白点（未发生点击），由调用方决定后续行为。
    """
    log = make_executor_log_fn(executor, log_callback)

    snapped_blank = snap_screen_point_to_canvas_background(
        executor,
        int(start_screen_x),
        int(start_screen_y),
        log_callback=log_callback,
        visual_callback=visual_callback,
    )
    if snapped_blank is None:
        log(f"{log_prefix}未在画布内找到可用空白点，跳过空白点击收尾")
        return False

    blank_screen_x, blank_screen_y = int(snapped_blank[0]), int(snapped_blank[1])
    log(f"{log_prefix}点击画布空白位置 screen=({blank_screen_x},{blank_screen_y})")
    click_and_verify(
        executor,
        blank_screen_x,
        blank_screen_y,
        f"{log_prefix}点击空白处",
        log_callback,
    )

    wait_value = float(wait_seconds)
    if wait_value > 0:
        effective_wait_message = wait_message or f"等待 {wait_value:.2f} 秒"
        log_wait_if_needed(
            executor,
            wait_value,
            effective_wait_message,
            log_callback,
            pause_hook,
            allow_continue,
        )

    return True


__all__ = [
    # 画布/颜色吸附相关常量
    "CANVAS_ALLOWED_COLORS",
    "CANVAS_COLOR_TOLERANCES",
    "CANVAS_COLOR_MAX_DISTANCES",
    "CANVAS_FALLBACK_GRID_STEPS_X",
    "CANVAS_FALLBACK_GRID_STEPS_Y",
    "CANVAS_SAFE_POINT_NEAR_MAX_RADIUS",
    "CANVAS_SAFE_POINT_NEAR_STEP",
    "CANVAS_RECT_SAMPLE_STEPS_X",
    "CANVAS_RECT_SAMPLE_STEPS_Y",
    # 画布吸附
    "snap_screen_point_to_canvas_background",
    "click_canvas_blank_near_screen_point",
    "make_executor_log_fn",
    # 运行时钩子与交互工具
    "is_fast_chain_runtime_enabled",
    "wait_with_hooks",
    "input_text_with_hooks",
    "right_click_with_hooks",
    "click_and_verify",
    "log_wait_if_needed",
    "find_template_on_row",
]


