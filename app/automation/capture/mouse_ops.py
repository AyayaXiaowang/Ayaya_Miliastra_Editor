# -*- coding: utf-8 -*-
"""
鼠标操作模块
负责鼠标点击和拖拽操作
"""

import ctypes
import threading
import atexit
from ctypes import wintypes
from typing import Tuple, Optional

from ..input.win_input import (
    move_mouse_absolute,
    left_down,
    left_up,
    right_down,
    right_up,
    iter_linear_drag_points,
    scroll_wheel_notches,
)
from ..input.common import sleep_seconds
from engine.configs.settings import settings


_block_guard_timer = None
_block_guard_active = False
_block_guard_exit_registered = False

_CLICK_PROFILE = {
    'left': {
        'classic': {'pre_down': 0.01, 'between': 0.01},
        'hybrid': {'pre_down': 0.01, 'between': 0.01},
    },
    'right': {
        'classic': {'pre_down': 0.05, 'between': 0.06},
        'hybrid': {'pre_down': 0.01, 'between': 0.02},
    },
}

_CLASSIC_DRAG_PROFILE = {
    'left': {'pre_down': 0.05, 'before_move': 0.05, 'before_up': 0.1},
    'right': {'pre_down': 0.05, 'before_move': 0.2, 'before_up': 0.2},
}


def _block_user_input(enable: bool) -> bool:
    """阻止或允许用户输入"""
    user32 = ctypes.windll.user32
    user32.BlockInput.argtypes = [wintypes.BOOL]
    user32.BlockInput.restype = wintypes.BOOL
    return bool(user32.BlockInput(1 if enable else 0))


def _register_block_guard_exit() -> None:
    global _block_guard_exit_registered
    if not _block_guard_exit_registered:
        atexit.register(_end_input_block_guard)
        _block_guard_exit_registered = True


def _begin_input_block_guard(timeout_seconds: float = 5.0) -> bool:
    """开始输入阻止保护"""
    global _block_guard_timer, _block_guard_active
    _register_block_guard_exit()
    _block_user_input(False)
    _block_guard_active = _block_user_input(True)
    t = threading.Timer(float(timeout_seconds), lambda: _block_user_input(False))
    t.daemon = True
    t.start()
    _block_guard_timer = t
    return _block_guard_active


def _end_input_block_guard() -> None:
    """结束输入阻止保护"""
    global _block_guard_timer, _block_guard_active
    if _block_guard_timer is not None:
        _block_guard_timer.cancel()
        _block_guard_timer = None
    _block_user_input(False)
    _block_guard_active = False


def _get_button_actions(button: str):
    """根据按键返回对应的按下/抬起函数。button in {'left','right'}"""
    b = str(button).lower()
    if b == 'left':
        return left_down, left_up
    if b == 'right':
        return right_down, right_up
    raise ValueError(f"未知的鼠标按键: {button}")


def _hybrid_click_generic(button: str, screen_x: int, screen_y: int, pre_down_sleep: float, between_sleep: float, post_release_sleep: float) -> bool:
    """混合模式：瞬移到目标点击，完成后复位光标（参数化左右键与延时）。"""
    down_fn, up_fn = _get_button_actions(button)
    orig_x, orig_y = get_cursor_pos()
    moved = move_mouse_absolute(int(screen_x), int(screen_y))
    if not moved:
        return False
    sleep_seconds(float(pre_down_sleep))
    if not down_fn():
        return False
    sleep_seconds(float(between_sleep))
    if not up_fn():
        return False
    sleep_seconds(float(post_release_sleep))
    _ = move_mouse_absolute(int(orig_x), int(orig_y))
    return True


def _classic_click_generic(button: str, screen_x: int, screen_y: int, pre_down_sleep: float, between_sleep: float) -> bool:
    """经典模式：移动到目标点击，结束后不复位（参数化左右键与延时）。"""
    down_fn, up_fn = _get_button_actions(button)
    moved = move_mouse_absolute(int(screen_x), int(screen_y))
    if not moved:
        return False
    sleep_seconds(float(pre_down_sleep))
    ok_down = down_fn()
    if not ok_down:
        return False
    sleep_seconds(float(between_sleep))
    ok_up = up_fn()
    if not ok_up:
        return False
    return True


def _hybrid_drag_generic(button: str, screen_x1: int, screen_y1: int, screen_x2: int, screen_y2: int, *, pre_down_sleep: float, steps: int, per_step_sleep: float, step_end_sleep: float, post_release_sleep: float) -> bool:
    """混合模式拖拽：步进平滑，结束后复位（参数化左右键与延时/步数）。"""
    down_fn, up_fn = _get_button_actions(button)
    orig_x, orig_y = get_cursor_pos()
    start_ok = move_mouse_absolute(int(screen_x1), int(screen_y1))
    if not start_ok:
        return False
    sleep_seconds(float(pre_down_sleep))
    if not down_fn():
        return False
    sleep_seconds(float(pre_down_sleep))
    total_steps = int(steps)
    for xi, yi in iter_linear_drag_points(
        int(screen_x1),
        int(screen_y1),
        int(screen_x2),
        int(screen_y2),
        total_steps,
    ):
        _ = move_mouse_absolute(int(xi), int(yi))
        sleep_seconds(float(per_step_sleep))
    sleep_seconds(float(step_end_sleep))
    if not up_fn():
        return False
    sleep_seconds(float(post_release_sleep))
    _ = move_mouse_absolute(int(orig_x), int(orig_y))
    return True


def _stepped_drag_generic(
    button: str,
    screen_x1: int,
    screen_y1: int,
    screen_x2: int,
    screen_y2: int,
    *,
    pre_down_sleep: float,
    steps: int,
    per_step_sleep: float,
    step_end_sleep: float,
    post_release_sleep: float,
    reset_cursor: bool,
) -> bool:
    """步进拖拽：用于需要“拖拽持续时长”更可控的场景（可选复位）。"""
    down_fn, up_fn = _get_button_actions(button)
    if bool(reset_cursor):
        orig_x, orig_y = get_cursor_pos()
    else:
        orig_x, orig_y = (0, 0)

    start_ok = move_mouse_absolute(int(screen_x1), int(screen_y1))
    if not start_ok:
        return False
    sleep_seconds(float(pre_down_sleep))
    if not down_fn():
        return False
    sleep_seconds(float(pre_down_sleep))

    total_steps = int(steps)
    if total_steps <= 0:
        raise ValueError("steps must be positive")

    for xi, yi in iter_linear_drag_points(
        int(screen_x1),
        int(screen_y1),
        int(screen_x2),
        int(screen_y2),
        total_steps,
    ):
        _ = move_mouse_absolute(int(xi), int(yi))
        if float(per_step_sleep) > 0.0:
            sleep_seconds(float(per_step_sleep))

    if float(step_end_sleep) > 0.0:
        sleep_seconds(float(step_end_sleep))

    if not up_fn():
        return False

    if float(post_release_sleep) > 0.0:
        sleep_seconds(float(post_release_sleep))

    if bool(reset_cursor):
        _ = move_mouse_absolute(int(orig_x), int(orig_y))

    return True


def _instant_drag_generic(button: str, screen_x1: int, screen_y1: int, screen_x2: int, screen_y2: int, *, pre_down_sleep: float, before_move_sleep: float, before_up_sleep: float) -> bool:
    """瞬移拖拽：按下后瞬移到终点再松开（参数化左右键与延时）。"""
    down_fn, up_fn = _get_button_actions(button)
    moved = move_mouse_absolute(int(screen_x1), int(screen_y1))
    if not moved:
        return False
    sleep_seconds(float(pre_down_sleep))
    ok_down = down_fn()
    if not ok_down:
        return False
    sleep_seconds(float(before_move_sleep))
    moved2 = move_mouse_absolute(int(screen_x2), int(screen_y2))
    if not moved2:
        return False
    sleep_seconds(float(before_up_sleep))
    ok_up = up_fn()
    if not ok_up:
        return False
    return True


def _classic_drag_generic(button: str, screen_x1: int, screen_y1: int, screen_x2: int, screen_y2: int, *, pre_down_sleep: float, before_move_sleep: float, before_up_sleep: float) -> bool:
    """经典拖拽：移动到起点→按下→移动到终点→抬起（参数化左右键与延时）。"""
    down_fn, up_fn = _get_button_actions(button)
    moved = move_mouse_absolute(int(screen_x1), int(screen_y1))
    if not moved:
        return False
    sleep_seconds(float(pre_down_sleep))
    ok_down = down_fn()
    if not ok_down:
        return False
    sleep_seconds(float(before_move_sleep))
    moved2 = move_mouse_absolute(int(screen_x2), int(screen_y2))
    if not moved2:
        return False
    sleep_seconds(float(before_up_sleep))
    ok_up = up_fn()
    if not ok_up:
        return False
    return True


def _click_button(button: str, screen_x: int, screen_y: int, *, post_release_sleep_override: Optional[float] = None) -> bool:
    _begin_input_block_guard(5.0)
    try:
        mode = str(getattr(settings, 'MOUSE_EXECUTION_MODE', 'classic'))
        profile = _CLICK_PROFILE[button]
        if mode == 'hybrid':
            cfg = profile['hybrid']
            post_release_sleep = (
                float(post_release_sleep_override)
                if post_release_sleep_override is not None
                else float(getattr(settings, 'MOUSE_HYBRID_POST_RELEASE_SLEEP', 0.15))
            )
            return bool(
                _hybrid_click_generic(
                    button,
                    int(screen_x),
                    int(screen_y),
                    pre_down_sleep=float(cfg['pre_down']),
                    between_sleep=float(cfg['between']),
                    post_release_sleep=post_release_sleep,
                )
            )
        cfg = profile['classic']
        return bool(
            _classic_click_generic(
                button,
                int(screen_x),
                int(screen_y),
                pre_down_sleep=float(cfg['pre_down']),
                between_sleep=float(cfg['between']),
            )
        )
    finally:
        _end_input_block_guard()


def click_right_button(screen_x: int, screen_y: int, *, post_release_sleep: Optional[float] = None) -> bool:
    """右键单击：根据模式选择 classic/hybrid，并在操作期间锁定用户输入。"""
    return _click_button('right', screen_x, screen_y, post_release_sleep_override=post_release_sleep)


def click_left_button(screen_x: int, screen_y: int, *, post_release_sleep: Optional[float] = None) -> bool:
    """左键单击：根据模式选择 classic/hybrid，并在操作期间锁定用户输入。"""
    return _click_button('left', screen_x, screen_y, post_release_sleep_override=post_release_sleep)


def _hybrid_drag(button: str, screen_x1: int, screen_y1: int, screen_x2: int, screen_y2: int, *, post_release_sleep: Optional[float] = None) -> bool:
    post_sleep = (
        float(post_release_sleep)
        if post_release_sleep is not None
        else float(getattr(settings, 'MOUSE_HYBRID_POST_RELEASE_SLEEP', 0.15))
    )
    return _hybrid_drag_generic(
        button,
        int(screen_x1), int(screen_y1), int(screen_x2), int(screen_y2),
        pre_down_sleep=0.01,
        steps=int(getattr(settings, 'MOUSE_HYBRID_STEPS', 40)),
        per_step_sleep=float(getattr(settings, 'MOUSE_HYBRID_STEP_SLEEP', 0.008)),
        step_end_sleep=0.005,
        post_release_sleep=post_sleep,
    )


def _drag_button_timed(
    button: str,
    screen_x1: int,
    screen_y1: int,
    screen_x2: int,
    screen_y2: int,
    *,
    duration_seconds: float,
    steps: int,
    post_release_sleep_override: Optional[float] = None,
) -> bool:
    """定时步进拖拽：用于“拖拽不生效/疑似卡顿”时让拖拽更慢、更稳。"""
    total_steps = int(steps)
    if total_steps <= 0:
        raise ValueError("steps must be positive")
    duration = float(duration_seconds)
    if duration < 0.0:
        raise ValueError("duration_seconds must be non-negative")

    _begin_input_block_guard(5.0)
    try:
        mode = str(getattr(settings, 'MOUSE_EXECUTION_MODE', 'classic'))
        reset_cursor = bool(mode == 'hybrid')

        if post_release_sleep_override is not None:
            post_release_sleep = float(post_release_sleep_override)
        else:
            post_release_sleep = (
                float(getattr(settings, 'MOUSE_HYBRID_POST_RELEASE_SLEEP', 0.15))
                if reset_cursor
                else 0.0
            )

        per_step_sleep = float(duration) / float(total_steps)
        return bool(
            _stepped_drag_generic(
                button,
                int(screen_x1),
                int(screen_y1),
                int(screen_x2),
                int(screen_y2),
                pre_down_sleep=0.01,
                steps=total_steps,
                per_step_sleep=per_step_sleep,
                step_end_sleep=0.005,
                post_release_sleep=float(post_release_sleep),
                reset_cursor=bool(reset_cursor),
            )
        )
    finally:
        _end_input_block_guard()


def _drag_button(button: str, screen_x1: int, screen_y1: int, screen_x2: int, screen_y2: int, *, post_release_sleep_override: Optional[float] = None) -> bool:
    _begin_input_block_guard(5.0)
    try:
        drag_mode = str(getattr(settings, 'MOUSE_DRAG_MODE', 'auto'))
        if drag_mode == 'stepped':
            return bool(_hybrid_drag(button, screen_x1, screen_y1, screen_x2, screen_y2, post_release_sleep=post_release_sleep_override))
        if drag_mode == 'instant':
            cfg = _CLASSIC_DRAG_PROFILE[button]
            return bool(
                _instant_drag_generic(
                    button,
                    int(screen_x1), int(screen_y1), int(screen_x2), int(screen_y2),
                    pre_down_sleep=float(cfg['pre_down']),
                    before_move_sleep=float(cfg['before_move']),
                    before_up_sleep=float(cfg['before_up']),
                )
            )
        mode = str(getattr(settings, 'MOUSE_EXECUTION_MODE', 'classic'))
        if mode == 'hybrid':
            return bool(_hybrid_drag(button, screen_x1, screen_y1, screen_x2, screen_y2, post_release_sleep=post_release_sleep_override))
        cfg = _CLASSIC_DRAG_PROFILE[button]
        return bool(
            _classic_drag_generic(
                button,
                int(screen_x1), int(screen_y1), int(screen_x2), int(screen_y2),
                pre_down_sleep=float(cfg['pre_down']),
                before_move_sleep=float(cfg['before_move']),
                before_up_sleep=float(cfg['before_up']),
            )
        )
    finally:
        _end_input_block_guard()


def drag_right_button(screen_x1: int, screen_y1: int, screen_x2: int, screen_y2: int, *, post_release_sleep: Optional[float] = None) -> bool:
    """右键拖拽：根据拖拽策略或执行模式选择 instant/stepped；执行期间锁定用户输入。"""
    return _drag_button('right', screen_x1, screen_y1, screen_x2, screen_y2, post_release_sleep_override=post_release_sleep)


def drag_left_button(screen_x1: int, screen_y1: int, screen_x2: int, screen_y2: int, *, post_release_sleep: Optional[float] = None) -> bool:
    """左键拖拽：根据拖拽策略或执行模式选择 instant/stepped；执行期间锁定用户输入。"""
    return _drag_button('left', screen_x1, screen_y1, screen_x2, screen_y2, post_release_sleep_override=post_release_sleep)


def drag_right_button_timed(
    screen_x1: int,
    screen_y1: int,
    screen_x2: int,
    screen_y2: int,
    *,
    duration_seconds: float = 1.0,
    steps: int = 40,
    post_release_sleep: Optional[float] = None,
) -> bool:
    """右键拖拽（定时步进版）：按 duration_seconds 放慢拖拽节奏，提高拖拽生效概率。"""
    return _drag_button_timed(
        'right',
        int(screen_x1),
        int(screen_y1),
        int(screen_x2),
        int(screen_y2),
        duration_seconds=float(duration_seconds),
        steps=int(steps),
        post_release_sleep_override=post_release_sleep,
    )


def drag_left_button_timed(
    screen_x1: int,
    screen_y1: int,
    screen_x2: int,
    screen_y2: int,
    *,
    duration_seconds: float = 1.0,
    steps: int = 40,
    post_release_sleep: Optional[float] = None,
) -> bool:
    """左键拖拽（定时步进版）：按 duration_seconds 放慢拖拽节奏，提高拖拽生效概率。"""
    return _drag_button_timed(
        'left',
        int(screen_x1),
        int(screen_y1),
        int(screen_x2),
        int(screen_y2),
        duration_seconds=float(duration_seconds),
        steps=int(steps),
        post_release_sleep_override=post_release_sleep,
    )


def get_cursor_pos() -> Tuple[int, int]:
    """获取当前鼠标指针的屏幕坐标 (x,y)。"""
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    ok = ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    if ok == 0:
        return (0, 0)
    return (int(pt.x), int(pt.y))


def move_mouse(screen_x: int, screen_y: int) -> bool:
    """仅移动鼠标到指定屏幕坐标，不点击。"""
    return bool(move_mouse_absolute(int(screen_x), int(screen_y)))


def scroll_wheel(
    notches: int,
    *,
    per_notch_sleep: float = 0.01,
) -> None:
    """滚动鼠标滚轮（在当前位置）。

    说明：
    - 仅负责滚动，不负责移动鼠标；调用方应先将鼠标移动到期望滚动的区域上方；
    - 为保持节奏稳定，默认每格滚轮之间等待极短时间。
    """
    total = int(notches)
    if total == 0:
        return
    step = 1 if total > 0 else -1
    for _ in range(abs(total)):
        scroll_wheel_notches(int(step))
        if float(per_notch_sleep) > 0:
            sleep_seconds(float(per_notch_sleep))

