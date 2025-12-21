from __future__ import annotations

import sys
from functools import lru_cache
from typing import Iterable

from PyQt6 import QtGui, QtWidgets


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


@lru_cache(maxsize=1)
def _available_families() -> set[str]:
    """返回当前系统可用字体族集合。

    注意：QFontDatabase 依赖 QApplication/QGuiApplication 已创建。
    若在无 QApplication 的环境调用，本函数返回空集合并交由上层回退。
    """
    if QtWidgets.QApplication.instance() is None:
        return set()
    return set(QtGui.QFontDatabase.families())


def _pick_first_available_font_family(candidates: Iterable[str]) -> str:
    available_families = _available_families()
    for family in candidates:
        if family in available_families:
            return family

    # 回退：优先用应用默认字体（若已有 QApplication），否则用 Qt 默认字体。
    if QtWidgets.QApplication.instance() is not None:
        return QtWidgets.QApplication.font().family()
    return QtGui.QFont().family()


def _preferred_ui_families() -> list[str]:
    if _is_macos():
        return [
            "PingFang SC",
            "Hiragino Sans GB",
            "Heiti SC",
            "STHeiti",
            "Helvetica Neue",
            "Arial",
        ]
    if _is_windows():
        return [
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "Segoe UI",
        ]
    return [
        "Noto Sans CJK SC",
        "Noto Sans",
        "DejaVu Sans",
    ]


def _preferred_monospace_families() -> list[str]:
    if _is_macos():
        return [
            "SF Mono",
            "Menlo",
            "Monaco",
        ]
    if _is_windows():
        return [
            "Consolas",
            "Cascadia Mono",
            "Cascadia Code",
            "Courier New",
        ]
    return [
        "Noto Sans Mono",
        "DejaVu Sans Mono",
        "Liberation Mono",
        "Monospace",
    ]


def _preferred_emoji_families() -> list[str]:
    if _is_macos():
        return ["Apple Color Emoji"]
    if _is_windows():
        return ["Segoe UI Emoji"]
    return ["Noto Color Emoji"]


@lru_cache(maxsize=1)
def ui_font_family() -> str:
    """应用 UI 主字体族（按平台选择并确保存在）。"""
    return _pick_first_available_font_family(_preferred_ui_families())


@lru_cache(maxsize=1)
def monospace_font_family() -> str:
    """等宽字体族（按平台选择并确保存在）。"""
    return _pick_first_available_font_family(_preferred_monospace_families())


@lru_cache(maxsize=1)
def emoji_font_family() -> str:
    """Emoji 字体族（按平台选择并确保存在）。"""
    return _pick_first_available_font_family(_preferred_emoji_families())


def ui_font(point_size: int, *, bold: bool = False, italic: bool = False) -> QtGui.QFont:
    font = QtGui.QFont(ui_font_family(), int(point_size))
    font.setBold(bool(bold))
    font.setItalic(bool(italic))
    return font


def monospace_font(point_size: int, *, bold: bool = False, italic: bool = False) -> QtGui.QFont:
    font = QtGui.QFont(monospace_font_family(), int(point_size))
    font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    font.setBold(bool(bold))
    font.setItalic(bool(italic))
    return font


def emoji_font(point_size: int, *, bold: bool = False, italic: bool = False) -> QtGui.QFont:
    font = QtGui.QFont(emoji_font_family(), int(point_size))
    font.setBold(bool(bold))
    font.setItalic(bool(italic))
    return font


_font_substitutions_installed = False


def install_platform_font_substitutions() -> None:
    """安装常见字体族的跨平台替换表。

    目的：
    - macOS / Linux 上请求 Windows 字体名时，不触发“缺少字体”提示
    - 保持旧代码里历史遗留的字体族名也能正确回退
    """
    global _font_substitutions_installed
    if _font_substitutions_installed:
        return
    _font_substitutions_installed = True

    ui_family = ui_font_family()
    mono_family = monospace_font_family()
    emoji_family = emoji_font_family()

    _insert_substitutions("Microsoft YaHei UI", [ui_family])
    _insert_substitutions("Microsoft YaHei", [ui_family])
    _insert_substitutions("Consolas", [mono_family])
    _insert_substitutions("Segoe UI Emoji", [emoji_family])


def _insert_substitutions(source_family: str, target_families: list[str]) -> None:
    if not target_families:
        return
    QtGui.QFont.insertSubstitutions(source_family, target_families)




