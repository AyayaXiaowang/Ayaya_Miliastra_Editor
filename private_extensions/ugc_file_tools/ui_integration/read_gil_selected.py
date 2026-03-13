from __future__ import annotations

def on_read_clicked(main_window: object) -> None:
    """打开导入中心并预选 `.gil` 选择性导入任务。"""
    from .import_center import open_import_center_dialog

    open_import_center_dialog(main_window, preferred_task="gil_selected")
    return

