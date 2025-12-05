"""通用管理对话框骨架，统一标题/说明/按钮与样式。"""

from __future__ import annotations

from PyQt6 import QtGui, QtWidgets

from ui.foundation.theme_manager import ThemeManager, Colors


class ManagementDialogBase(QtWidgets.QDialog):
    """提供“标题 + 说明 + 内容区 + 关闭按钮”的统一结构。"""

    def __init__(
        self,
        *,
        title_text: str,
        info_text: str = "",
        width: int = 720,
        height: int = 520,
        close_button_text: str = "关闭",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title_text)
        self.resize(width, height)
        self.setModal(True)
        self.setStyleSheet(ThemeManager.dialog_surface_style(include_tables=True))

        self._main_layout = QtWidgets.QVBoxLayout(self)
        self._build_header(title_text, info_text)
        self._content_layout = QtWidgets.QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.addLayout(self._content_layout, 1)
        self._build_footer(close_button_text)

    def add_body_widget(self, widget: QtWidgets.QWidget) -> None:
        """将内容部件放入主体区域。"""
        self._content_layout.addWidget(widget)

    # -- private helpers -------------------------------------------------
    def _build_header(self, title_text: str, info_text: str) -> None:
        title_label = QtWidgets.QLabel(title_text)
        title_label.setFont(QtGui.QFont("Microsoft YaHei UI", 14, QtGui.QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; padding: 10px;")
        self._main_layout.addWidget(title_label)

        if info_text:
            info_label = QtWidgets.QLabel(info_text)
            info_label.setFont(QtGui.QFont("Microsoft YaHei UI", 9))
            info_label.setWordWrap(True)
            info_label.setStyleSheet(f"{ThemeManager.info_label_dark_style()} border-radius: 4px;")
            self._main_layout.addWidget(info_label)

    def _build_footer(self, close_button_text: str) -> None:
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        close_btn = QtWidgets.QPushButton(close_button_text, self)
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        self._main_layout.addLayout(button_layout)


