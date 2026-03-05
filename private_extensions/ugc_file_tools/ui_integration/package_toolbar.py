from __future__ import annotations


def install_ugc_file_tools_buttons(main_window: object) -> None:
    """在“项目存档（PACKAGES）”页工具栏注入 ugc_file_tools 的入口按钮。"""
    # 延迟导入：保证插件导入阶段尽量轻量
    from PyQt6 import QtWidgets

    from .export_wizard import on_open_import_export_center_clicked

    if not isinstance(main_window, QtWidgets.QMainWindow):
        raise TypeError(f"main_window 必须是 QMainWindow（got: {type(main_window).__name__}）")

    package_library_widget = getattr(main_window, "package_library_widget", None)
    if package_library_widget is None:
        raise RuntimeError("主窗口缺少 package_library_widget，无法注入读取/导出按钮")

    ensure_btn = getattr(package_library_widget, "ensure_extension_toolbar_button", None)
    if not callable(ensure_btn):
        raise RuntimeError(
            "PackageLibraryWidget 缺少 ensure_extension_toolbar_button，无法注入读取/导出按钮"
        )

    installed_flag = getattr(package_library_widget, "_ugc_file_tools_buttons_installed", None)
    if installed_flag is True:
        return
    setattr(package_library_widget, "_ugc_file_tools_buttons_installed", True)

    center_btn = ensure_btn(
        "ugc_file_tools.import_export_center",
        "导入/导出…",
        tooltip="打开 ugc_file_tools 导入/导出中心（GIL/GIA）",
        on_clicked=lambda: on_open_import_export_center_clicked(main_window),
        enabled=True,
    )
    setattr(package_library_widget, "_ugc_file_tools_center_btn", center_btn)


