from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets


class ScrollSafeComboBox(QtWidgets.QComboBox):
    """仅在获得焦点后才响应滚轮事件的下拉框，避免悬停时误改值。

    - 未聚焦时：忽略滚轮，事件交给父级滚动区域处理（例如字段表格或对话框）。
    - 已聚焦时：保持 Qt 默认行为，允许滚轮在当前输入控件上微调。
    """

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[override]
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class ClickToEditLineEdit(QtWidgets.QLineEdit):
    """仅在显式点击后才接管焦点的文本框，避免表格选中就开始输入。

    - 焦点策略限制为 ClickFocus：只接受鼠标点击获得焦点，Tab 等不会直接把焦点移入。
    - 适用于嵌入表格单元格的行内编辑控件，降低误输入风险。
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)


__all__ = ["ScrollSafeComboBox", "ClickToEditLineEdit"]


