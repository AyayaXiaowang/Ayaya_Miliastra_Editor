# -*- coding: utf-8 -*-
from PyQt6 import QtCore
from typing import Callable

from ui.foundation.debounce import Debouncer


class RefreshGate(QtCore.QObject):
    """统一的刷新门与防抖器。

    - `set_refreshing(True/False)` 用于在批量更新期间屏蔽由 UI 信号触发的递归刷新；
    - `debounce()` 通过组合 `Debouncer` 实现“仅执行最后一次提交的回调”，避免重复重建视图。
    """

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._refreshing: bool = False
        self._debouncer = Debouncer(self)

    def set_refreshing(self, refreshing: bool) -> None:
        self._refreshing = refreshing

    @property
    def is_refreshing(self) -> bool:
        return self._refreshing

    def debounce(self, delay_ms: int, callback: Callable[[], None]) -> None:
        """在指定延迟后触发一次回调，多次调用只保留最后一次。"""
        self._debouncer.debounce(delay_ms, callback)


