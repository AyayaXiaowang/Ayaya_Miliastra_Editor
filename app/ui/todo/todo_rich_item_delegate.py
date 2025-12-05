from typing import Any, Dict, List

from PyQt6 import QtCore, QtGui, QtWidgets

from ui.foundation.theme_manager import Colors


class RichTextItemDelegate(QtWidgets.QStyledItemDelegate):
    """基于 tokens 的自绘委托：使用 QPainter 绘制分段彩色文本，不再依赖 HTML/QTextDocument。

    约定：index.data(rich_role) 返回 List[Dict]（tokens），字段：
      - text: 文本内容（必需）
      - color: 文本颜色（必需，通常来自 ThemeColors/StepTypeColors）
      - bold: 是否加粗（可选）
      - bg: 背景色（可选，尽量仅用于动作词淡底）
    若无 tokens，则回退到默认绘制。
    """

    def __init__(
        self,
        rich_role: int,
        parent: QtWidgets.QWidget | None = None,
        dimmed_role: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._rich_role: int = int(rich_role)
        # 置灰标记角色：若未显式提供，则默认使用 rich_role 之后的一个自定义角色。
        self._dimmed_role: int = int(dimmed_role) if dimmed_role is not None else int(
            rich_role
        ) + 1

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        tokens = index.data(self._rich_role)
        if not isinstance(tokens, list) or len(tokens) == 0:
            super().paint(painter, option, index)
            return

        is_dimmed = bool(index.data(self._dimmed_role))

        # 让样式系统先绘制背景/选中态/复选框/图标等，再在文本区域内部自绘文字
        styled_option = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(styled_option, index)
        style = (
            styled_option.widget.style()
            if styled_option.widget is not None
            else QtWidgets.QApplication.style()
        )

        option_without_text = QtWidgets.QStyleOptionViewItem(styled_option)
        option_without_text.text = ""
        style.drawControl(
            QtWidgets.QStyle.ControlElement.CE_ItemViewItem,
            option_without_text,
            painter,
            styled_option.widget,
        )

        text_rect = style.subElementRect(
            QtWidgets.QStyle.SubElement.SE_ItemViewItemText,
            styled_option,
            styled_option.widget,
        )

        painter.save()
        painter.setClipRect(text_rect)

        base_font = styled_option.font
        font_metrics = QtGui.QFontMetrics(base_font)
        text_height = font_metrics.height()
        vertical_offset = text_rect.y() + (
            text_rect.height() - text_height
        ) // 2 + font_metrics.ascent()

        current_x = text_rect.x()
        maximum_x = text_rect.right()

        for raw_token in tokens:
            if not isinstance(raw_token, dict):
                continue
            text = str(raw_token.get("text", ""))
            if not text:
                continue

            base_color_value = str(raw_token.get("color", Colors.TEXT_PRIMARY))
            color_value = (
                Colors.TEXT_DISABLED if is_dimmed else base_color_value
            )
            background_value = raw_token.get("bg")
            is_bold = bool(raw_token.get("bold", False))

            token_font = QtGui.QFont(base_font)
            token_font.setBold(is_bold)
            token_metrics = QtGui.QFontMetrics(token_font)
            text_width = token_metrics.horizontalAdvance(text)

            if current_x > maximum_x:
                break

            # 轻量实现：为带背景色的 token 绘制一条紧贴文本高度的色块
            if background_value:
                background_color = QtGui.QColor(str(background_value))
                background_rect = QtCore.QRect(
                    current_x,
                    text_rect.y(),
                    text_width + 4,
                    text_rect.height(),
                )
                painter.fillRect(background_rect, background_color)

            painter.setFont(token_font)
            painter.setPen(QtGui.QColor(color_value))
            painter.drawText(current_x + 2, vertical_offset, text)

            current_x += text_width + 4

        painter.restore()

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtCore.QSize:
        # 高度沿用默认，实现与系统行高一致
        return super().sizeHint(option, index)

    def editorEvent(
        self,
        event: QtCore.QEvent,
        model: QtCore.QAbstractItemModel,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> bool:
        """处理复选框交互：
        - 仅当项可用户勾选时响应
        - 只在点击复选框本体时切换勾选状态；点击行文本仅改变选中
        """
        # 仅处理左键释放以避免多次切换
        if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
            mouse_event = event  # type: ignore[assignment]
            # PyQt6 鼠标事件位置属性兼容
            position = (
                mouse_event.position().toPoint()
                if hasattr(mouse_event, "position")
                else mouse_event.pos()
            )  # type: ignore[attr-defined]
            if hasattr(mouse_event, "button") and mouse_event.button() == QtCore.Qt.MouseButton.LeftButton:
                item_flags = index.flags()
                # 仅叶子项具备此标志；父项不可直接勾选
                if item_flags & QtCore.Qt.ItemFlag.ItemIsUserCheckable:
                    style_option = QtWidgets.QStyleOptionViewItem(option)
                    self.initStyleOption(style_option, index)
                    style = (
                        style_option.widget.style()
                        if style_option.widget is not None
                        else QtWidgets.QApplication.style()
                    )
                    check_rectangle = style.subElementRect(
                        QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator,
                        style_option,
                        style_option.widget,
                    )
                    # 只在点击复选框区域时切换勾选状态
                    if check_rectangle.contains(position):
                        current_state = index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
                        new_state = (
                            QtCore.Qt.CheckState.Unchecked
                            if current_state == QtCore.Qt.CheckState.Checked
                            else QtCore.Qt.CheckState.Checked
                        )
                        return model.setData(
                            index,
                            new_state,
                            QtCore.Qt.ItemDataRole.CheckStateRole,
                        )
        return super().editorEvent(event, model, option, index)


