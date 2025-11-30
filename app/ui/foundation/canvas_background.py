"""Utility helpers for drawing scene backgrounds."""

from PyQt6 import QtGui


def draw_grid_background(painter, rect, grid_size: int = 50) -> None:
    """Render a dark grid background used by QGraphicsScene."""
    painter.fillRect(rect, QtGui.QColor("#1E1E1E"))

    left = int(rect.left()) - (int(rect.left()) % grid_size)
    top = int(rect.top()) - (int(rect.top()) % grid_size)

    light_grid_pen = QtGui.QPen(QtGui.QColor("#2A2A2A"), 1)
    painter.setPen(light_grid_pen)

    x = left
    while x < rect.right():
        painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
        x += grid_size

    y = top
    while y < rect.bottom():
        painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
        y += grid_size

    thick_grid_pen = QtGui.QPen(QtGui.QColor("#3A3A3A"), 2)
    painter.setPen(thick_grid_pen)

    x = left
    while x < rect.right():
        if int(x) % (grid_size * 5) == 0:
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
        x += grid_size

    y = top
    while y < rect.bottom():
        if int(y) % (grid_size * 5) == 0:
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
        y += grid_size


