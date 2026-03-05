"""
界面控件设置（Web-first）

该右侧面板用于管理模式的“🖼️ 界面控件组” section：
- 不再在 PyQt 内维护复杂的预览/编辑 UI；
- 统一提供“打开 UI 工作台（Web）”入口，浏览器侧负责查看/导入/预览。
"""

from __future__ import annotations

from typing import Optional

from PyQt6 import QtGui, QtWidgets

from app.ui.panels.panel_scaffold import PanelScaffold, SectionCard


class UIControlSettingsPanel(PanelScaffold):
    """界面控件设置面板（放置于主窗口右侧全局 Tab）。"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="界面控件设置（Web）",
            description="该模块已迁移为 Web-first：在浏览器中查看/导入 UI 布局与控件模板。",
        )
        self.bound_manager: Optional[QtWidgets.QWidget] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        entry = SectionCard("UI 工作台（插件）", "入口由私有扩展提供（避免主程序与插件重复维护两份前端）")
        container = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        hint = QtWidgets.QLabel(
            "提示：界面控件组的 Web-first 工具已迁移到私有扩展：\n"
            "- `private_extensions/千星沙箱网页处理工具/`\n\n"
            "请在 管理 → 🖼️ 界面控件组 页面使用插件注入的工具条按钮打开浏览器页面。",
            container,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color: rgba(255,255,255,0.72);" if self._looks_like_dark_theme() else "color: rgba(0,0,0,0.72);"
        )
        layout.addWidget(hint)

        layout.addStretch(1)
        entry.add_content_widget(container)
        self.body_layout.addWidget(entry)
        self.body_layout.addStretch(1)

    # ------------------------------------------------------------------ compatibility
    def bind_manager(self, manager: QtWidgets.QWidget) -> None:
        """兼容旧接口：历史上会绑定 UIControlGroupManager 以接收预览信号。"""
        self.bound_manager = manager

    @staticmethod
    def _looks_like_dark_theme() -> bool:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return True
        palette = app.palette()
        window_color = palette.color(QtGui.QPalette.ColorRole.Window)
        return window_color.lightness() < 128


