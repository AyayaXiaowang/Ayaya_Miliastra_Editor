"""全局 Toast 通知相关的事件处理 Mixin。"""

from __future__ import annotations

from app.ui.foundation.toast_notification import ToastNotification


class ToastMixin:
    """封装主窗口级 Toast 通知显示入口。"""

    def _show_toast(self, message: str, toast_type: str) -> None:
        """显示 Toast 通知"""
        ToastNotification.show_message(self, message, toast_type)


