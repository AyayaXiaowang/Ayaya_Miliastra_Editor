from __future__ import annotations


def on_export_gia_clicked(main_window: object) -> None:
    """兼容入口：历史“导出节点图 .gia”独立对话框已收敛到导出中心。"""
    from .export_wizard import on_open_export_center_clicked

    on_open_export_center_clicked(main_window, preferred_format="gia")

