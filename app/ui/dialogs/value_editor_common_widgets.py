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
        # 记录“可编辑状态下”是否希望显示清除按钮（X）。
        # 只读/禁用时无论外部是否调用 setClearButtonEnabled(True)，都不应展示清除按钮。
        self._preferred_clear_button_enabled: bool | None = None

    def setClearButtonEnabled(self, enabled: bool) -> None:  # type: ignore[override]
        """设置清除按钮偏好，并根据当前可编辑状态决定是否展示。

        约定：
        - 只读或禁用时：强制隐藏清除按钮，避免在“禁止编辑”的表格中出现误导性的 X；
        - 恢复可编辑后：按调用方最近一次设置的偏好恢复展示与否。
        """
        self._preferred_clear_button_enabled = bool(enabled)
        self._sync_clear_button_visibility()

    def setReadOnly(self, read_only: bool) -> None:  # type: ignore[override]
        super().setReadOnly(read_only)
        self._sync_clear_button_visibility()

    def setEnabled(self, enabled: bool) -> None:  # type: ignore[override]
        super().setEnabled(enabled)
        self._sync_clear_button_visibility()

    def _sync_clear_button_visibility(self) -> None:
        """根据 read-only / enabled 状态同步清除按钮可见性。"""
        if self.isReadOnly() or (not self.isEnabled()):
            # 使用 super() 以避免污染“偏好状态”与触发递归。
            super().setClearButtonEnabled(False)
            return
        if self._preferred_clear_button_enabled is None:
            return
        super().setClearButtonEnabled(self._preferred_clear_button_enabled)


__all__ = ["ScrollSafeComboBox", "ClickToEditLineEdit"]


