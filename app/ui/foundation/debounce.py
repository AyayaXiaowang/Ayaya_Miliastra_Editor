from __future__ import annotations

from PyQt6 import QtCore
from typing import Callable, Optional


class Debouncer(QtCore.QObject):
    """
    通用防抖器：延迟一段时间后只执行最后一次提交的回调。
    - 使用单次 QTimer
    - 多次调用 debounce() 会替换回调并重新计时
    """

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._callback: Optional[Callable[[], None]] = None
        self._timer.timeout.connect(self._run)

    def _run(self) -> None:
        cb = self._callback
        self._callback = None
        if cb is not None:
            cb()

    def debounce(self, delay_ms: int, callback: Callable[[], None]) -> None:
        self._callback = callback
        self._timer.stop()
        self._timer.start(delay_ms)

    def cancel(self) -> None:
        self._timer.stop()
        self._callback = None


