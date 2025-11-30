from __future__ import annotations

"""
窗口查找工具：为 capture 与 input 模块提供统一的 HWND 获取逻辑。
"""

import ctypes


def find_window_handle(window_title: str, *, case_sensitive: bool = False) -> int:
    """按标题精确/模糊匹配顶层窗口，返回 HWND（找不到返回 0）。"""
    if not isinstance(window_title, str) or window_title.strip() == "":
        return 0

    user32 = ctypes.windll.user32
    # 先尝试精确匹配
    exact_hwnd = user32.FindWindowW(None, ctypes.c_wchar_p(window_title))
    if int(exact_hwnd) != 0 and user32.IsWindowVisible(exact_hwnd):
        return int(exact_hwnd)

    target = window_title if case_sensitive else window_title.lower()
    found = ctypes.c_void_p(0)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_proc(hwnd, _lparam):
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
    return int(found.value) if found.value else 0

