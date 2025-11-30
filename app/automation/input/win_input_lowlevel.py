# -*- coding: utf-8 -*-
"""
Windows 低层输入封装（仅本进程内使用）

职责：
- 统一封装 SendInput/屏幕坐标归一化，避免在上层重复定义 ctypes 结构与常量；
- 提供最小原语：绝对移动、左/右键按下与抬起；
- 不负责 sleep/时序控制，时序由上层调用者决定。

约束：
- 不捕获/吞并异常；
- 仅在 Windows 平台工作；
- 返回布尔值指示是否调用成功（按 SendInput 返回值判定）。
"""

from __future__ import annotations

import ctypes


# 常量（与 WinUser.h 对齐）
MOUSEEVENTF_MOVE: int = 0x0001
MOUSEEVENTF_LEFTDOWN: int = 0x0002
MOUSEEVENTF_LEFTUP: int = 0x0004
MOUSEEVENTF_RIGHTDOWN: int = 0x0008
MOUSEEVENTF_RIGHTUP: int = 0x0010
MOUSEEVENTF_ABSOLUTE: int = 0x8000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", INPUT_UNION),
    ]


def _screen_metrics() -> tuple[int, int]:
    user32 = ctypes.windll.user32
    return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def _normalize_to_absolute(screen_x: int, screen_y: int) -> tuple[int, int]:
    width, height = _screen_metrics()
    abs_x = int(int(screen_x) * 65535 / width)
    abs_y = int(int(screen_y) * 65535 / height)
    return abs_x, abs_y


def _send_inputs(inputs: list[INPUT]) -> bool:
    count = len(inputs)
    arr_type = INPUT * count
    arr = arr_type(*inputs)
    sent = ctypes.windll.user32.SendInput(count, ctypes.byref(arr), ctypes.sizeof(INPUT))
    return int(sent) == int(count)


def move_mouse_absolute(screen_x: int, screen_y: int) -> bool:
    """将鼠标移动到屏幕绝对坐标 (x, y)。"""
    abs_x, abs_y = _normalize_to_absolute(int(screen_x), int(screen_y))
    move_input = INPUT()
    move_input.type = 0
    move_input.mi.dx = int(abs_x)
    move_input.mi.dy = int(abs_y)
    move_input.mi.mouseData = 0
    move_input.mi.dwFlags = int(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
    move_input.mi.time = 0
    move_input.mi.dwExtraInfo = None
    return _send_inputs([move_input])


def left_down() -> bool:
    inp = INPUT()
    inp.type = 0
    inp.mi.dx = 0
    inp.mi.dy = 0
    inp.mi.mouseData = 0
    inp.mi.dwFlags = int(MOUSEEVENTF_LEFTDOWN)
    inp.mi.time = 0
    inp.mi.dwExtraInfo = None
    return _send_inputs([inp])


def left_up() -> bool:
    inp = INPUT()
    inp.type = 0
    inp.mi.dx = 0
    inp.mi.dy = 0
    inp.mi.mouseData = 0
    inp.mi.dwFlags = int(MOUSEEVENTF_LEFTUP)
    inp.mi.time = 0
    inp.mi.dwExtraInfo = None
    return _send_inputs([inp])


def right_down() -> bool:
    inp = INPUT()
    inp.type = 0
    inp.mi.dx = 0
    inp.mi.dy = 0
    inp.mi.mouseData = 0
    inp.mi.dwFlags = int(MOUSEEVENTF_RIGHTDOWN)
    inp.mi.time = 0
    inp.mi.dwExtraInfo = None
    return _send_inputs([inp])


def right_up() -> bool:
    inp = INPUT()
    inp.type = 0
    inp.mi.dx = 0
    inp.mi.dy = 0
    inp.mi.mouseData = 0
    inp.mi.dwFlags = int(MOUSEEVENTF_RIGHTUP)
    inp.mi.time = 0
    inp.mi.dwExtraInfo = None
    return _send_inputs([inp])



