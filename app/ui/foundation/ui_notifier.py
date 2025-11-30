from __future__ import annotations

"""通用 UI 通知工具。

职责：
- 提供统一的 Toast 提示入口，避免在各业务组件中重复处理 main_window/父窗口选择逻辑。
- 不关心具体业务页面，只依赖 QtWidgets 与 `ToastNotification`。
"""

from typing import Protocol, runtime_checkable

from PyQt6 import QtWidgets

from ui.foundation.toast_notification import ToastNotification


@runtime_checkable
class HasMainWindow(Protocol):
    """简单协议：提供 main_window 属性的 UI 容器。

    约定：大部分复杂面板或控制器都暴露 main_window，以便统一决定 Toast 的归属窗口。
    """

    main_window: QtWidgets.QWidget  # type: ignore[assignment]


def _resolve_parent_widget(ui_context: QtWidgets.QWidget | HasMainWindow | object) -> QtWidgets.QWidget | None:
    """从任意 UI 上下文中解析出适合作为 Toast 父级的 QWidget。"""
    if isinstance(ui_context, QtWidgets.QWidget):
        return ui_context

    if isinstance(ui_context, HasMainWindow) and isinstance(ui_context.main_window, QtWidgets.QWidget):
        return ui_context.main_window

    return None


def notify(ui_context: QtWidgets.QWidget | HasMainWindow | object, message: str, toast_type: str = "info") -> None:
    """在合适的父窗口上显示一条 Toast 提示。

    优先选择：
    1) ui_context.main_window（若实现 HasMainWindow 且为 QWidget）
    2) 传入的 ui_context 本身（若为 QWidget）

    若无法找到合适的父窗口，仅在控制台打印消息。
    """
    print(message, flush=True)

    parent_widget = _resolve_parent_widget(ui_context)
    if parent_widget is None:
        return

    ToastNotification.show_message(parent_widget, message, toast_type)


