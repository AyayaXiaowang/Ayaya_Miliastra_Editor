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
    # 运行时钩子与交互工具
    "is_fast_chain_runtime_enabled",
    "wait_with_hooks",
    "input_text_with_hooks",
    "right_click_with_hooks",
    "click_and_verify",
    "log_wait_if_needed",
    "find_template_on_row",
]


