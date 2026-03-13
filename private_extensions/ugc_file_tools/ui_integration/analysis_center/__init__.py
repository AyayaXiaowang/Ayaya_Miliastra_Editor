from __future__ import annotations


def open_analysis_center_dialog(main_window: object) -> None:
    """打开 ugc_file_tools 分析中心（非模态三步对话框）。"""
    from .dialog import open_analysis_center_dialog as _open

    _open(main_window)

