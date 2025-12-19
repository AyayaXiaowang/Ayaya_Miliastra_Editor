# -*- coding: utf-8 -*-
"""
工具函数模块
提供字体、文本输入、窗口操作等辅助功能
"""

import os
from pathlib import Path
from typing import List
from PIL import ImageFont
from ..input.common import sleep_seconds


def _get_candidate_system_font_dirs() -> List[Path]:
    candidate_dirs: List[Path] = []

    windows_root_text = str(os.environ.get("WINDIR") or os.environ.get("SystemRoot") or "").strip()
    if windows_root_text:
        candidate_dirs.append(Path(windows_root_text) / "Fonts")

    # macOS 常见目录
    candidate_dirs.append(Path("/System/Library/Fonts"))
    candidate_dirs.append(Path("/Library/Fonts"))

    # Linux 常见目录
    candidate_dirs.append(Path("/usr/share/fonts"))
    candidate_dirs.append(Path("/usr/local/share/fonts"))

    user_home_dir = Path.home()
    candidate_dirs.append(user_home_dir / ".fonts")
    candidate_dirs.append(user_home_dir / ".local" / "share" / "fonts")
    candidate_dirs.append(user_home_dir / "Library" / "Fonts")

    # 去重（保持顺序）
    seen: set[str] = set()
    unique_dirs: List[Path] = []
    for candidate_dir in candidate_dirs:
        candidate_dir_text = str(candidate_dir)
        if candidate_dir_text in seen:
            continue
        seen.add(candidate_dir_text)
        unique_dirs.append(candidate_dir)
    return unique_dirs


def get_chinese_font(size: int = 16):
    """获取中文字体。

    优先级：
    1) 环境变量 GRAPH_GENERATER_CHINESE_FONT_PATH 指定的字体文件
    2) 系统字体目录中探测常见中文字体文件名
    3) PIL 默认字体
    """
    explicit_font_path_text = str(os.environ.get("GRAPH_GENERATER_CHINESE_FONT_PATH", "") or "").strip()
    if explicit_font_path_text:
        explicit_font_path = Path(explicit_font_path_text)
        if not explicit_font_path.exists():
            raise FileNotFoundError(f"未找到中文字体文件：{explicit_font_path}")
        return ImageFont.truetype(str(explicit_font_path), size)

    candidate_font_file_names = [
        # Windows 常见中文字体
        "msyh.ttc",
        "msyh.ttf",
        "simhei.ttf",
        "simsun.ttc",
        "simkai.ttf",
        # macOS / Linux 常见中文字体
        "PingFang.ttc",
        "PingFang SC.ttf",
        "NotoSansCJK-Regular.ttc",
        "NotoSansCJK-Regular.otf",
    ]

    for font_dir in _get_candidate_system_font_dirs():
        for font_file_name in candidate_font_file_names:
            candidate_font_path = font_dir / font_file_name
            if candidate_font_path.exists():
                return ImageFont.truetype(str(candidate_font_path), size)

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

