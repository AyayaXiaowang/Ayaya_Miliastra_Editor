from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation import fonts as ui_fonts
from app.ui.graph.graph_palette import GraphPalette


class PortTypePopupItem(QtWidgets.QGraphicsItem):
    """画布内轻量气泡：用于展示端口类型等短文本信息。

    设计目标：
    - 非模态：不阻塞交互，不使用 QMessageBox。
    - 轻量：QGraphicsItem 自绘，不引入 QGraphicsProxyWidget。
    - 风格统一：沿用 GraphPalette 深色系与圆角卡片风格。
    """

    PADDING_X = 10
    PADDING_Y = 8
    RADIUS = 8
    LINE_SPACING = 2

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self._lines = [str(x) for x in (lines or []) if str(x).strip()]
        if not self._lines:
            self._lines = ["类型：<未知>"]

        self._font = ui_fonts.ui_font(9)
        fm = QtGui.QFontMetrics(self._font)
        line_height = int(fm.height())
        max_width = max((int(fm.horizontalAdvance(line)) for line in self._lines), default=0)

        width = int(max_width + self.PADDING_X * 2)
        height = int(len(self._lines) * line_height + (len(self._lines) - 1) * self.LINE_SPACING + self.PADDING_Y * 2)

        self._rect = QtCore.QRectF(0.0, 0.0, float(width), float(height))

        # 不响应鼠标事件，避免遮挡端口/连线交互
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
        self.setZValue(10_000)  # 高于端口与按钮

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(self._rect)

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        rect = self.boundingRect()

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        bg = QtGui.QColor(GraphPalette.NODE_CONTENT_BG)
        bg.setAlpha(235)
        border = QtGui.QColor(GraphPalette.BORDER_SUBTLE)

        painter.setPen(QtGui.QPen(border, 1))
        painter.setBrush(QtGui.QBrush(bg))
        painter.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        painter.setFont(self._font)
        painter.setPen(QtGui.QColor(GraphPalette.TEXT_BRIGHT))

        fm = painter.fontMetrics()
        line_height = int(fm.height())

        x = float(self.PADDING_X)
        y = float(self.PADDING_Y)
        for idx, line in enumerate(self._lines):
            baseline = y + float(line_height) * (idx + 1) + float(self.LINE_SPACING) * idx - float(fm.descent())
            painter.drawText(QtCore.QPointF(x, baseline), line)


__all__ = ["PortTypePopupItem"]


