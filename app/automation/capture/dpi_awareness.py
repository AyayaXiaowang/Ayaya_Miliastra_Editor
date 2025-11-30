# -*- coding: utf-8 -*-
"""
DPI 感知模块
负责在 Windows 环境下设置进程级 DPI 感知
"""

import ctypes

# 进程级DPI感知只需设置一次
_dpi_awareness_initialized = False


def ensure_dpi_awareness_once():
    """仅在当前进程未开启 Per-Monitor DPI 感知时设置一次"""
    global _dpi_awareness_initialized
    if _dpi_awareness_initialized:
        return
    # 查询当前进程 DPI 感知
    awareness = ctypes.c_int()
    hprocess = ctypes.windll.kernel32.GetCurrentProcess()
    # GetProcessDpiAwareness 返回 0 表示成功
    result = ctypes.windll.shcore.GetProcessDpiAwareness(hprocess, ctypes.byref(awareness))
    if result == 0 and awareness.value == 2:
        _dpi_awareness_initialized = True
        return
    # 若未开启，则设置为 Per-Monitor DPI 感知
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    _dpi_awareness_initialized = True


def set_dpi_awareness():
    """兼容旧调用名：内部转到一次性设置"""
    ensure_dpi_awareness_once()

