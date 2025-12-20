from __future__ import annotations

"""
窗口查找工具：为 capture 与 input 模块提供统一的 HWND 获取逻辑。
"""

import ctypes
from ctypes import wintypes


def find_window_handle(window_title: str, *, case_sensitive: bool = False) -> int:
    """按标题精确/模糊匹配顶层窗口，返回 HWND（找不到返回 0）。"""
    if not isinstance(window_title, str) or window_title.strip() == "":
        return 0

    user32 = ctypes.windll.user32
    # Win64 关键：明确声明 WinAPI 的签名，避免 ctypes 默认把参数当作 32 位 c_int，
    # 导致 HWND 句柄在回调或函数调用中溢出（OverflowError: int too long to convert）。
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL

    # 先尝试精确匹配
    exact_hwnd = user32.FindWindowW(None, ctypes.c_wchar_p(window_title))
    if int(exact_hwnd) != 0 and user32.IsWindowVisible(exact_hwnd):
        return int(exact_hwnd)

    target = window_title if case_sensitive else window_title.lower()
    found = wintypes.HWND(0)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd: wintypes.HWND, _lparam: wintypes.LPARAM):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if int(length) <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(int(length) + 1)
        user32.GetWindowTextW(hwnd, buffer, int(length) + 1)
        current = buffer.value
        compare_text = current if case_sensitive else current.lower()
        if target in compare_text:
            found.value = hwnd
            return False
        return True

    user32.EnumWindows(enum_proc, 0)
    return int(found.value) if int(found.value) != 0 else 0

