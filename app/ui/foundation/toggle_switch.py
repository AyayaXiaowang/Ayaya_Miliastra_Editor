"""基础开关控件：用于替代传统勾选框的左右滑动开关按钮。

- 继承自 `QCheckBox`，保留 `stateChanged` / `toggled` 等信号兼容性
- 不显示文本内容，标签文字交由外层 `QLabel` 或表单标签负责
- 尺寸与配色依赖全局主题 `Sizes` 与 `Colors`，保证在不同面板中的统一视觉风格
"""

from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from ui.foundation.theme_manager import ThemeManager, Sizes


class ToggleSwitch(QtWidgets.QCheckBox):
    """左右滑动样式的布尔开关。

    该控件仅绘制一个带圆角的轨道与滑块，适合作为“是/否”“启用/禁用”等布尔选项的输入部件。
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        base_height = max(int(Sizes.INPUT_HEIGHT * 0.8), 20)
        self._height = base_height
        self._width = int(base_height * 2.0)
        self._margin = max(int(base_height * 0.15), 3)

        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.setText("")
        self.setTristate(False)
        self.setChecked(False)
        self.setMinimumSize(self._width, self._height)

    def sizeHint(self) -> QtCore.QSize:  # type: ignore[override]
        return QtCore.QSize(self._width, self._height)

    def hitButton(self, pos: QtCore.QPoint) -> bool:  # type: ignore[override]
        """扩大点击区域：整个控件矩形内点击都视为命中。

        避免只在默认的“指示器”区域可点，导致右半边看起来是开关但点了没有反应。
        """
        return self.rect().contains(pos)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        rect = self.rect()
        track_rect = QtCore.QRect(
            self._margin,
            self._margin,
            rect.width() - 2 * self._margin,
            rect.height() - 2 * self._margin,
        )
        radius = track_rect.height() // 2

        if self.isChecked():
            # 使用水平方向的主色系渐变，起点/终点使用浮点坐标以兼容 Qt6 的 QLinearGradient 签名
            gradient = QtGui.QLinearGradient(
                float(track_rect.left()),
                float(track_rect.center().y()),
                float(track_rect.right()),
                float(track_rect.center().y()),
            )
            gradient.setColorAt(
                0.0, QtGui.QColor(ThemeManager.Colors.PRIMARY_DARK)
            )
            gradient.setColorAt(
                1.0, QtGui.QColor(ThemeManager.Colors.PRIMARY_LIGHT)
            )
            track_brush = QtGui.QBrush(gradient)
            thumb_color = QtGui.QColor(ThemeManager.Colors.TEXT_ON_PRIMARY)
        else:
            track_color = QtGui.QColor(ThemeManager.Colors.BG_DISABLED)
            track_brush = QtGui.QBrush(track_color)
            thumb_color = QtGui.QColor(ThemeManager.Colors.TEXT_SECONDARY)

        if not self.isEnabled():
            thumb_color.setAlphaF(0.6)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(track_brush)
        painter.drawRoundedRect(track_rect, radius, radius)

        thumb_diameter = track_rect.height() - 2 * self._margin
        thumb_rect = QtCore.QRect(0, 0, thumb_diameter, thumb_diameter)

        center_y = track_rect.center().y()
        if self.isChecked():
            center_x = track_rect.right() - radius
        else:
            center_x = track_rect.left() + radius

        thumb_rect.moveCenter(QtCore.QPoint(center_x, center_y))

        painter.setBrush(thumb_color)
        painter.drawEllipse(thumb_rect)

        if self.hasFocus():
            focus_pen = QtGui.QPen(QtGui.QColor(ThemeManager.Colors.BORDER_FOCUS))
            focus_pen.setWidth(1)
            painter.setPen(focus_pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            focus_rect = track_rect.adjusted(-1, -1, 1, 1)
            painter.drawRoundedRect(focus_rect, radius, radius)


__all__ = ["ToggleSwitch"]


