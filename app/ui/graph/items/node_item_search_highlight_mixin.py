"""NodeGraphicsItem：画布搜索命中高亮（Ctrl+F）相关逻辑。"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation.theme_manager import Colors


class NodeSearchHighlightMixin:
    # === 搜索高亮（Ctrl+F） ===

    def set_search_highlighted(self, highlighted: bool) -> None:
        """设置“搜索命中”高亮描边（不改变选中状态）。"""
        new_state = bool(highlighted)
        if bool(getattr(self, "_search_highlighted", False)) == new_state:
            return
        self._search_highlighted = new_state
        self.update()

    def _paint_search_highlight_outline(
        self,
        painter: QtGui.QPainter,
        rect: QtCore.QRectF,
        *,
        corner_radius: float,
    ) -> None:
        """绘制搜索命中描边（仅对未选中节点生效）。"""
        if not bool(getattr(self, "_search_highlighted", False)):
            return
        if self.isSelected():
            return
        pen = QtGui.QPen(QtGui.QColor(Colors.INFO_LIGHT))
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            rect.adjusted(-2.0, -2.0, 2.0, 2.0),
            float(corner_radius + 2.0),
            float(corner_radius + 2.0),
        )

