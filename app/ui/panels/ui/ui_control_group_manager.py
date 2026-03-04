"""
界面控件组入口页（插件化）。

说明：
- 本仓库不再内置一套完整的 Web Workbench 静态资源（避免与私有扩展重复维护两份前端）。
- 实际的 HTML→UI bundle 导出 / 导入能力由私有扩展提供：
  `private_extensions/千星沙箱网页处理工具/`。
- 主程序内该页面仅保留说明与引导文案，避免“找不到 assets/ui_workbench”之类的误导弹窗。
"""

from __future__ import annotations

from typing import Optional, Union

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView

__all__ = ["UIControlGroupManager"]


class UIControlGroupManager(QtWidgets.QWidget):
    """管理模式“🖼️ 界面控件组”专用页面：仅提供 Web Workbench 入口。"""

    # 保留信号：右侧面板/历史 binder 仍会尝试连接这些信号
    open_player_editor_requested = QtCore.pyqtSignal()
    widget_selected = QtCore.pyqtSignal(str, str)
    widget_moved = QtCore.pyqtSignal(str, str, float, float)
    widget_resized = QtCore.pyqtSignal(str, str, float, float)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.current_package: Optional[Union[PackageView, GlobalResourceView]] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("界面控件组（Web）", self)
        font = title.font()
        font.setPointSize(max(10, int(font.pointSize() * 1.15)))
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        desc = QtWidgets.QLabel(
            "该模块已迁移为 Web-first（插件化）：HTML→UI bundle 的导出/导入在浏览器中完成。\n"
            "主程序内不再内置完整 Workbench 前端资源；请使用私有扩展：千星沙箱网页处理工具。",
            self,
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            "color: rgba(255,255,255,0.72);" if self._looks_like_dark_theme() else "color: rgba(0,0,0,0.72);"
        )
        layout.addWidget(desc)

        hint = QtWidgets.QLabel(
            "使用方式：\n"
            "- 启用私有扩展 `private_extensions/千星沙箱网页处理工具/plugin.py`\n"
            "- 进入 管理 → 🖼️ 界面控件组 页面后，在工具条按钮中打开：\n"
            "  - UI控件组预览（Web）\n",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color: rgba(255,255,255,0.72);" if self._looks_like_dark_theme() else "color: rgba(0,0,0,0.72);"
        )
        layout.addWidget(hint)

        buttons_row = QtWidgets.QHBoxLayout()
        buttons_row.setSpacing(10)

        btn_preview = QtWidgets.QPushButton("打开 UI控件组预览（Web）", self)
        buttons_row.addWidget(btn_preview)
        buttons_row.addStretch(1)
        layout.addLayout(buttons_row)

        btn_preview.clicked.connect(self._open_ui_preview)

        layout.addStretch(1)

    def set_package(self, package: Union[PackageView, GlobalResourceView]) -> None:
        # 仅用于保持对外协议一致（Web Workbench 会从主程序 API 读取上下文）
        self.current_package = package

    def _open_ui_preview(self) -> None:
        from app.ui.controllers.ui_pages_browser import open_ui_preview_browser_or_raise

        open_ui_preview_browser_or_raise(main_window=self.window())

    @staticmethod
    def _looks_like_dark_theme() -> bool:
        # 基于 palette 的粗略判断：避免引入 ThemeManager 依赖循环
        app = QtWidgets.QApplication.instance()
        if app is None:
            return True
        palette = app.palette()
        window_color = palette.color(QtGui.QPalette.ColorRole.Window)
        return window_color.lightness() < 128

