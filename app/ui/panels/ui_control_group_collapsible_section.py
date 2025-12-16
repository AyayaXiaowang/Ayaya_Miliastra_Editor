from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.theme_manager import Colors, Sizes

__all__ = ["CollapsibleSection"]


class _ClickableHeader(QtWidgets.QWidget):
    """带点击信号的简单头部控件，避免直接覆写事件处理。"""

    clicked = QtCore.pyqtSignal()

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class CollapsibleSection(QtWidgets.QWidget):
    """可折叠内容分组，带箭头展开/收起动画效果。"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)

        self.is_collapsed = False

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.header = _ClickableHeader()
        self.header.setObjectName("CollapsibleSectionHeader")
        self.header.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.header.clicked.connect(self.toggle)
        header_layout = QtWidgets.QHBoxLayout(self.header)
        header_layout.setContentsMargins(
            Sizes.PADDING_SMALL, Sizes.PADDING_SMALL, Sizes.PADDING_SMALL, Sizes.PADDING_SMALL
        )

        self.arrow_label = QtWidgets.QLabel("▼")
        self.arrow_label.setObjectName("CollapsibleSectionArrow")
        self.arrow_label.setStyleSheet(
            f"""
            QLabel#CollapsibleSectionArrow {{
                color: {Colors.TEXT_SECONDARY};
                font-size: {Sizes.FONT_NORMAL + 2}px;
            }}
        """
        )
        self.arrow_label.setFixedWidth(20)
        header_layout.addWidget(self.arrow_label)

        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet(
            f"""
            color: {Colors.TEXT_PRIMARY};
            font-weight: bold;
            font-size: {Sizes.FONT_NORMAL + 1}px;
        """
        )
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.header.setStyleSheet(
            """
            QWidget#CollapsibleSectionHeader {
                background-color: transparent;
                border: none;
            }
            QWidget#CollapsibleSectionHeader:hover {
                background-color: %s;
            }
        """
            % Colors.BG_SELECTED
        )

        main_layout.addWidget(self.header)

        self.content_widget = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(
            Sizes.PADDING_SMALL, Sizes.PADDING_SMALL, Sizes.PADDING_SMALL, Sizes.PADDING_SMALL
        )
        self.content_layout.setSpacing(Sizes.SPACING_SMALL)

        main_layout.addWidget(self.content_widget)

    def toggle(self):
        """切换展开/折叠状态。"""
        self.is_collapsed = not self.is_collapsed
        self.content_widget.setVisible(not self.is_collapsed)
        self.arrow_label.setText("▶" if self.is_collapsed else "▼")

    def setCollapsed(self, collapsed: bool):
        """直接设置折叠状态。"""
        self.is_collapsed = collapsed
        self.content_widget.setVisible(not collapsed)
        self.arrow_label.setText("▶" if collapsed else "▼")

    def add_widget(self, widget: QtWidgets.QWidget):
        """向内容区域添加子控件。"""
        self.content_layout.addWidget(widget)

    def clear_content(self) -> None:
        """移除内容区的所有子控件，便于重复复用。"""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            child_widget = item.widget()
            if child_widget:
                child_widget.setParent(None)

