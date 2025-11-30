from __future__ import annotations

from PyQt6 import QtWidgets


def scroll_to_bottom(widget: QtWidgets.QWidget) -> None:
    """
    将可滚动控件滚动到底部。
    适配 QTextEdit / QPlainTextEdit / QAbstractScrollArea 及其子类。
    """
    # QTextEdit/QPlainTextEdit/QTextBrowser 等直接有 verticalScrollBar()
    if hasattr(widget, "verticalScrollBar"):
        sb = widget.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())
            return
    # 其他 QAbstractScrollArea 子类
    if isinstance(widget, QtWidgets.QAbstractScrollArea):
        sb = widget.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())
            return
    raise ValueError("该控件不支持滚动或未找到 verticalScrollBar()")


