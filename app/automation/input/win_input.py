from __future__ import annotations

"""
Windows 输入高层封装（本进程内使用）

职责：
- 提供客户区→屏幕坐标换算与客户区拖拽；
- 提供中文友好的文本输入（UNICODE）；
- 复用低层 `win_input_lowlevel` 的鼠标原语，保证实现性一致性；

约束：
- 不捕获异常；失败时让系统调用抛错或自行返回；
- 坐标单位统一为“像素”；
"""

from dataclasses import dataclass
from typing import Tuple, Iterator
import ctypes

from ctypes import wintypes

from .win_input_lowlevel import (
    move_mouse_absolute,
    left_down,
    left_up,
    right_down,
    right_up,
)
from .common import sleep_seconds
from .window_finder import find_window_handle


@dataclass
class ClientRect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return int(self.right - self.left)

    @property
    def height(self) -> int:
        return int(self.bottom - self.top)


def find_window_by_title(window_title: str) -> int:
    """先精确匹配，失败则子串匹配；不可见窗口忽略。"""
    return find_window_handle(window_title, case_sensitive=True)


def get_client_rect(hwnd: int) -> ClientRect:
    rect = wintypes.RECT()
    r = ctypes.windll.user32.GetClientRect(int(hwnd), ctypes.byref(rect))
    if int(r) == 0:
        raise RuntimeError("GetClientRect failed")

    origin = wintypes.POINT(0, 0)
    r2 = ctypes.windll.user32.ClientToScreen(int(hwnd), ctypes.byref(origin))
    if int(r2) == 0:
        raise RuntimeError("ClientToScreen failed")

    left = int(origin.x)
    top = int(origin.y)
    right = left + int(rect.right - rect.left)
    bottom = top + int(rect.bottom - rect.top)
    return ClientRect(left=left, top=top, right=right, bottom=bottom)


def client_to_screen(hwnd: int, client_x: int, client_y: int) -> Tuple[int, int]:
    point = wintypes.POINT(int(client_x), int(client_y))
    ok = ctypes.windll.user32.ClientToScreen(int(hwnd), ctypes.byref(point))
    if int(ok) == 0:
        raise RuntimeError("ClientToScreen failed")
    return int(point.x), int(point.y)


def _set_cursor_pos(screen_x: int, screen_y: int) -> None:
    # 使用绝对坐标统一路径，复用 SendInput 归一化流程
    move_mouse_absolute(int(screen_x), int(screen_y))


def move_mouse_client(hwnd: int, client_x: int, client_y: int) -> None:
    screen_x, screen_y = client_to_screen(int(hwnd), int(client_x), int(client_y))
    _set_cursor_pos(screen_x, screen_y)


def drag_client(
    hwnd: int,
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    steps: int = 30,
    step_sleep_ms: int = 6,
) -> None:
    move_mouse_client(int(hwnd), int(start_x), int(start_y))
    if not left_down():
        raise RuntimeError("left_down failed")
    for intermediate_x, intermediate_y in iter_linear_drag_points(
        int(start_x),
        int(start_y),
        int(end_x),
        int(end_y),
        int(steps),
    ):
        move_mouse_client(int(hwnd), int(intermediate_x), int(intermediate_y))
        if int(step_sleep_ms) > 0:
            sleep_seconds(int(step_sleep_ms) / 1000.0)
    if not left_up():
        raise RuntimeError("left_up failed")


def iter_linear_drag_points(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    steps: int,
) -> Iterator[Tuple[int, int]]:
    total_steps = int(steps)
    if total_steps <= 0:
        raise ValueError("steps must be positive")
    delta_x = int(end_x) - int(start_x)
    delta_y = int(end_y) - int(start_y)
    for index in range(1, total_steps + 1):
        ratio = index / float(total_steps)
        intermediate_x = int(start_x + delta_x * ratio)
        intermediate_y = int(start_y + delta_y * ratio)
        yield intermediate_x, intermediate_y


# --- 键盘 UNICODE 输入 ---

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    )


class INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = (
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        )

    _anonymous_ = ("u",)
    _fields_ = (("type", ctypes.c_ulong), ("u", _INPUT_UNION))


def _send_inputs(input_list: list[INPUT]) -> None:
    if len(input_list) == 0:
        return
    input_count = ctypes.c_uint(len(input_list))
    pointer = (INPUT * len(input_list))(*input_list)
    sent = ctypes.windll.user32.SendInput(input_count, pointer, ctypes.sizeof(INPUT))
    if int(sent) != len(input_list):
        raise RuntimeError("SendInput failed")


def send_text(text: str, per_char_sleep_ms: int = 1) -> None:
    if text is None or len(text) == 0:
        return
    inputs: list[INPUT] = []
    for character in text:
        scan_code = ord(character)
        key_down = INPUT()
        key_down.type = INPUT_KEYBOARD
        key_down.ki = KEYBDINPUT(0, scan_code, KEYEVENTF_UNICODE, 0, None)

        key_up = INPUT()
        key_up.type = INPUT_KEYBOARD
        key_up.ki = KEYBDINPUT(0, scan_code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)

        inputs.append(key_down)
        inputs.append(key_up)

    _send_inputs(inputs)
    if int(per_char_sleep_ms) > 0:
        sleep_seconds(int(per_char_sleep_ms) / 1000.0)


def press_enter() -> None:
    inputs: list[INPUT] = []
    key_down = INPUT()
    key_down.type = INPUT_KEYBOARD
    key_down.ki = KEYBDINPUT(0x0D, 0, 0, 0, None)

    key_up = INPUT()
    key_up.type = INPUT_KEYBOARD
    key_up.ki = KEYBDINPUT(0x0D, 0, KEYEVENTF_KEYUP, 0, None)

    inputs.append(key_down)
    inputs.append(key_up)
    _send_inputs(inputs)



