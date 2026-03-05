from __future__ import annotations

from pathlib import Path

from app.common.private_extension_registry import register_main_window_hook
from engine.utils.logging.logger import log_info


def install(workspace_root: Path) -> None:
    # 可选：插件安装时的初始化入口（此处仅做示例日志）
    log_info("[PRIVATE-EXT][example_import_export_package] install: workspace_root={}", str(workspace_root))


@register_main_window_hook
def _install_menu(main_window: object) -> None:
    # 延迟导入：保证插件导入阶段尽量轻量
    from PyQt6 import QtGui, QtWidgets

    if not isinstance(main_window, QtWidgets.QMainWindow):
        raise TypeError(f"main_window 必须是 QMainWindow（got: {type(main_window).__name__}）")

    package_controller = getattr(main_window, "package_controller", None)
    if package_controller is None:
        raise RuntimeError("主窗口缺少 package_controller，无法注入导入/导出菜单")

    import_fn = getattr(package_controller, "import_package", None)
    if not callable(import_fn):
        raise RuntimeError("package_controller.import_package 不存在或不可调用")

    export_fn = getattr(package_controller, "export_package", None)
    if not callable(export_fn):
        raise RuntimeError("package_controller.export_package 不存在或不可调用")

    menu_bar = main_window.menuBar()
    private_menu = menu_bar.addMenu("内部工具")

    import_action = QtGui.QAction("导入存档（示例）", main_window)
    import_action.setToolTip("调用 PackageController.import_package(...)（打开文件选择框导入索引 JSON）")
    import_action.triggered.connect(lambda: import_fn(main_window))
    private_menu.addAction(import_action)

    export_action = QtGui.QAction("导出当前存档（示例）", main_window)
    export_action.setToolTip("调用 PackageController.export_package(...)（导出当前存档为 JSON）")
    export_action.triggered.connect(lambda: export_fn(main_window))
    private_menu.addAction(export_action)


