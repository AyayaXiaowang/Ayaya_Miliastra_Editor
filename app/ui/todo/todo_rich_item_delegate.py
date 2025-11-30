from PyQt6 import QtWidgets, QtGui, QtCore
from typing import List, Dict, Any


class RichTextItemDelegate(QtWidgets.QStyledItemDelegate):
    """基于 HTML 的富文本绘制委托（与右侧日志一致的渲染路径）。

    约定：index.data(rich_role) 返回 List[Dict]（tokens），字段：
      - text: 文本内容（必需）
      - color: 文本颜色 #RRGGBB（必需）
      - bold: 是否加粗（可选）
      - bg: 背景色（可选，尽量仅用于动作词淡底）
    若无 tokens，则回退到默认绘制。
    """

    def __init__(self, rich_role: int, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._rich_role: int = int(rich_role)

    def _escape_html(self, text: str) -> str:
        return (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace("\"", "&quot;"))

    def _tokens_to_html(self, tokens: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        for tk in tokens:
            if not isinstance(tk, dict):
                continue
            raw = str(tk.get("text", ""))
            if raw == "":
                continue
            color = str(tk.get("color", "#333333"))
            is_bold = bool(tk.get("bold", False))
            bg = str(tk.get("bg", "")) if tk.get("bg") else ""
            style_items: List[str] = [f"color:{color}"]
            if is_bold:
                style_items.append("font-weight:600")
            if bg:
                # Qt rich text支持 background-color；不保证圆角，这里不使用 border-radius
                style_items.append(f"background-color:{bg}")
                style_items.append("padding:0 2px")
            style = ";".join(style_items)
            parts.append(f"<span style='{style}'>{self._escape_html(raw)}</span>")
        return "".join(parts)

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> None:
        tokens = index.data(self._rich_role)
        if not isinstance(tokens, list) or len(tokens) == 0:
            super().paint(painter, option, index)
            return

        # 准备样式与文本矩形（让系统先画背景/选中/复选框/展开箭头/图标）
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget is not None else QtWidgets.QApplication.style()

        # 先绘制除文本外的所有元素
        opt_no_text = QtWidgets.QStyleOptionViewItem(opt)
        opt_no_text.text = ""
        style.drawControl(QtWidgets.QStyle.ControlElement.CE_ItemViewItem, opt_no_text, painter, opt.widget)

        text_rect = style.subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)

        # 将 tokens 转为 HTML，并用 QTextDocument 绘制（与右侧日志一致的通路）
        html = self._tokens_to_html(tokens)
        if not html:
            return

        doc = QtGui.QTextDocument()
        doc.setDefaultFont(opt.font)
        doc.setHtml(html)

        painter.save()
        painter.setClipRect(text_rect)
        painter.translate(text_rect.topLeft())
        doc.drawContents(painter, QtCore.QRectF(0.0, 0.0, float(text_rect.width()), float(text_rect.height())))
        painter.restore()

    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> QtCore.QSize:
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
            pos = mouse_event.position().toPoint() if hasattr(mouse_event, "position") else mouse_event.pos()  # type: ignore[attr-defined]
            if hasattr(mouse_event, "button") and mouse_event.button() == QtCore.Qt.MouseButton.LeftButton:
                flags = index.flags()
                # 仅叶子项具备此标志；父项不可直接勾选
                if flags & QtCore.Qt.ItemFlag.ItemIsUserCheckable:
                    opt = QtWidgets.QStyleOptionViewItem(option)
                    self.initStyleOption(opt, index)
                    style = opt.widget.style() if opt.widget is not None else QtWidgets.QApplication.style()
                    check_rect = style.subElementRect(
                        QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator,
                        opt,
                        opt.widget,
                    )
                    # 只在点击复选框区域时切换勾选状态
                    if check_rect.contains(pos):
                        current = index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
                        new_state = (
                            QtCore.Qt.CheckState.Unchecked
                            if current == QtCore.Qt.CheckState.Checked
                            else QtCore.Qt.CheckState.Checked
                        )
                        return model.setData(index, new_state, QtCore.Qt.ItemDataRole.CheckStateRole)
        return super().editorEvent(event, model, option, index)


