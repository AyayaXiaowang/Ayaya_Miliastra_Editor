"""Proxy style to render a flat, themed down-arrow for combo boxes (and similar arrows)."""

from PyQt6 import QtCore, QtGui, QtWidgets

from ui.foundation.theme.tokens import Colors


class ComboArrowProxyStyle(QtWidgets.QProxyStyle):
    """Draws a flat triangle arrow using theme colors, avoiding QSS image hacks."""

    def drawPrimitive(
        self,
        element: QtWidgets.QStyle.PrimitiveElement,
        option: QtWidgets.QStyleOption,
        painter: QtGui.QPainter,
        widget: QtWidgets.QWidget | None = None,
    ) -> None:  # type: ignore[override]
        if element == QtWidgets.QStyle.PrimitiveElement.PE_IndicatorArrowDown:
            painter.save()
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

            is_enabled = bool(option.state & QtWidgets.QStyle.StateFlag.State_Enabled)
            color = QtGui.QColor(
                Colors.TEXT_SECONDARY if is_enabled else Colors.TEXT_DISABLED
            )
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QBrush(color))

            rect = option.rect
            size = min(rect.width(), rect.height(), 12)
            half_width = size * 0.4
            half_height = size * 0.35
            center = rect.center()

            points = [
                QtCore.QPointF(center.x() - half_width, center.y() - half_height),
                QtCore.QPointF(center.x() + half_width, center.y() - half_height),
                QtCore.QPointF(center.x(), center.y() + half_height),
            ]
            painter.drawPolygon(QtGui.QPolygonF(points))
            painter.restore()
            return

        super().drawPrimitive(element, option, painter, widget)

