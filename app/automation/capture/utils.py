# -*- coding: utf-8 -*-
"""
工具函数模块
提供字体、文本输入、窗口操作等辅助功能
"""

import os
from PIL import ImageFont
from ..input.common import sleep_seconds


def get_chinese_font(size=16):
    """获取中文字体"""
    font_paths = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\simkai.ttf",
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    
    return ImageFont.load_default()


def input_text(text: str) -> bool:
    """根据设置选择文本输入方式：clipboard / sendinput（UNICODE）。"""
    from engine.configs.settings import settings
    method = str(getattr(settings, 'TEXT_INPUT_METHOD', 'clipboard'))
    if method == 'sendinput':
        from ..input.win_input import send_text
        # SendInput 路径：按字符注入，支持中文，速度快且不依赖剪贴板
        send_text(str(text or ""), per_char_sleep_ms=1)
        return True
    # 默认：剪贴板 + Ctrl+V
    return input_text_via_clipboard(str(text or ""))


def input_text_via_clipboard(text: str) -> bool:
    """使用剪贴板+Ctrl+V方式输入文本"""
    import pyperclip
    import keyboard
    
    pyperclip.copy(text)
    sleep_seconds(0.1)
    keyboard.press_and_release('ctrl+v')
    return True


# 将 get_window_rect 从 screen_capture 移到这里，避免循环导入
def get_window_rect(window_title: str):
    """获取指定标题的窗口位置和尺寸（转发到 screen_capture）"""
    from .screen_capture import get_window_rect as _get_window_rect
    return _get_window_rect(window_title)

