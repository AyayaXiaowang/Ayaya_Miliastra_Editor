"""共享资源徽章：用于在列表项中以“徽章/图标”方式标注共享资源归属。

背景：
- 节点图库的卡片会在名称右侧显示“共享”徽章；
- 其它资源列表页（元件库/实体摆放/复合节点库等）也可能在“当前项目视图”中混入共享资源，
  为避免用户误判归属，需要提供一致、可复用的共享标记能力。

设计：
- 通过统一的 `SHARED_RESOURCE_BADGE_ROLE` 在 Qt item data 中标记是否共享；
- 通过 `SharedResourceBadgeDelegate` 在 QListWidget/QListView 的右侧绘制“共享”徽章；
- 业务页只需：
  1) 给 item 写入 `item.setData(SHARED_RESOURCE_BADGE_ROLE, True/False)`
  2) 对列表控件调用 `install_shared_resource_badge_delegate(list_widget)`
"""

from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.theme_manager import Colors


# 统一共享标记 role：尽量使用较高偏移，避免与页面内的 UserRole+1/+2 等业务 role 冲突。
SHARED_RESOURCE_BADGE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 100


class SharedResourceBadgeDelegate(QtWidgets.QStyledItemDelegate):
    """为列表项绘制右侧“共享”徽章的 delegate。"""

    def __init__(self, parent: Optional[QtCore.QObject] = None, *, badge_text: str = "共享") -> None:
        super().__init__(parent)
        self._badge_text = str(badge_text or "共享")
        self._badge_font = ui_fonts.ui_font(8, bold=True)
        self._badge_padding_x = 8
        self._badge_padding_y = 2
        self._badge_margin_right = 10
        self._badge_gap = 10

    def paint(
        self,
        painter: Optional[QtGui.QPainter],
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        if painter is None:
            return

        view_option = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(view_option, index)

        style = (
            view_option.widget.style()
            if view_option.widget is not None
            else QtWidgets.QApplication.style()
        )

        text_value = str(view_option.text or "")
        view_option.text = ""

        # 先交给系统风格绘制背景/焦点/图标等（不绘制文本）。
        style.drawControl(
            QtWidgets.QStyle.ControlElement.CE_ItemViewItem,
            view_option,
            painter,
            view_option.widget,
        )

        # 再绘制文本：必要时为徽章预留空间（避免遮挡）
        text_rect = style.subElementRect(
            QtWidgets.QStyle.SubElement.SE_ItemViewItemText,
            view_option,
            view_option.widget,
        )

        is_shared = bool(index.data(SHARED_RESOURCE_BADGE_ROLE))
        badge_rect: Optional[QtCore.QRect] = None
        if is_shared:
            badge_rect = self._compute_badge_rect(option.rect)
            reserved_right = badge_rect.left() - self._badge_gap
            if reserved_right < text_rect.right():
                text_rect.setRight(reserved_right)

        elided_text = QtGui.QFontMetrics(view_option.font).elidedText(
            text_value,
            QtCore.Qt.TextElideMode.ElideRight,
            max(0, text_rect.width()),
        )
        text_role = (
            QtGui.QPalette.ColorRole.HighlightedText
            if (view_option.state & QtWidgets.QStyle.StateFlag.State_Selected)
            else QtGui.QPalette.ColorRole.Text
        )
        style.drawItemText(
            painter,
            text_rect,
            int(view_option.displayAlignment),
            view_option.palette,
            bool(view_option.state & QtWidgets.QStyle.StateFlag.State_Enabled),
            elided_text,
            text_role,
        )

        # 绘制“共享”徽章
        if is_shared and badge_rect is not None:
            self._paint_badge(painter, badge_rect)

    def _compute_badge_rect(self, item_rect: QtCore.QRect) -> QtCore.QRect:
        metrics = QtGui.QFontMetrics(self._badge_font)
        text_width = metrics.horizontalAdvance(self._badge_text)
        badge_width = text_width + self._badge_padding_x * 2
        badge_height = metrics.height() + self._badge_padding_y * 2
        x = item_rect.x() + item_rect.width() - self._badge_margin_right - badge_width
        y = item_rect.y() + int((item_rect.height() - badge_height) / 2)
        return QtCore.QRect(int(x), int(y), int(badge_width), int(badge_height))

    def _paint_badge(self, painter: QtGui.QPainter, badge_rect: QtCore.QRect) -> None:
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setFont(self._badge_font)

        background_color = QtGui.QColor(Colors.ACCENT)
        text_color = QtGui.QColor(Colors.TEXT_ON_PRIMARY)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(background_color))

        radius = float(badge_rect.height()) / 2.0
        painter.drawRoundedRect(QtCore.QRectF(badge_rect), radius, radius)

        painter.setPen(QtGui.QPen(text_color))
        painter.drawText(badge_rect, QtCore.Qt.AlignmentFlag.AlignCenter, self._badge_text)
        painter.restore()


def install_shared_resource_badge_delegate(view: QtWidgets.QAbstractItemView) -> None:
    """为目标 view 安装共享徽章 delegate（覆盖默认 delegate）。"""
    delegate = SharedResourceBadgeDelegate(view)
    view.setItemDelegate(delegate)


