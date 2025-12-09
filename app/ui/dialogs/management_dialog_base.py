"""通用管理对话框骨架，统一标题/说明/按钮与样式。"""

from __future__ import annotations

from PyQt6 import QtGui, QtWidgets

from ui.foundation.base_widgets import BaseDialog
from ui.foundation.theme_manager import ThemeManager, Colors


class ManagementDialogBase(BaseDialog):
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
        super().__init__(
            title=title_text,
            width=width,
            height=height,
            buttons=QtWidgets.QDialogButtonBox.StandardButton.Close,
            parent=parent,
        )

        self._body_layout = QtWidgets.QVBoxLayout()
        self._body_layout.setContentsMargins(0, 0, 0, 0)

        self._build_header(title_text, info_text)
        self.content_layout.addLayout(self._body_layout, 1)
        self._apply_close_button_label(close_button_text)

    def add_body_widget(self, widget: QtWidgets.QWidget) -> None:
        """将内容部件放入主体区域。"""
        self._body_layout.addWidget(widget)

    # -- private helpers -------------------------------------------------
    def _build_header(self, title_text: str, info_text: str) -> None:
        title_label = QtWidgets.QLabel(title_text)
        title_label.setFont(QtGui.QFont("Microsoft YaHei UI", 14, QtGui.QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; padding: 10px;")
        self.content_layout.insertWidget(0, title_label)

        if info_text:
            info_label = QtWidgets.QLabel(info_text)
            info_label.setFont(QtGui.QFont("Microsoft YaHei UI", 9))
            info_label.setWordWrap(True)
            info_label.setStyleSheet(f"{ThemeManager.info_label_dark_style()} border-radius: 4px;")
            self.content_layout.insertWidget(1, info_label)

    def _apply_close_button_label(self, close_button_text: str) -> None:
        close_button = self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setText(close_button_text)

