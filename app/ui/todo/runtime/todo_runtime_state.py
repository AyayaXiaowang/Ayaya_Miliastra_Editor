from __future__ import annotations

from PyQt6 import QtCore


class TodoRuntimeState(QtCore.QObject):
    """集中管理运行时状态（success/failed/skipped）与提示。

    - 仅存储叶子步骤的运行态；父级不记录状态。
    - 提供查询与更新接口，供树样式与执行桥接层使用。
    """

    status_changed = QtCore.pyqtSignal(str)  # todo_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._status_map: dict[str, str] = {}
        self._tooltips_map: dict[str, str] = {}

    def clear(self, todo_id: str) -> None:
        if todo_id in self._status_map:
            self._status_map.pop(todo_id, None)
            self._tooltips_map.pop(todo_id, None)
            self.status_changed.emit(todo_id)

    def mark_failed(self, todo_id: str, tooltip: str = "该步骤执行失败") -> None:
        self._status_map[todo_id] = "failed"
        self._tooltips_map[todo_id] = tooltip
        self.status_changed.emit(todo_id)

    def mark_skipped(self, todo_id: str, reason: str = "该步骤因端点距离过远被跳过") -> None:
        self._status_map[todo_id] = "skipped"
        self._tooltips_map[todo_id] = reason
        self.status_changed.emit(todo_id)

    def mark_success(self, todo_id: str) -> None:
        # 运行成功不单独标记，由“复选框完成态”表达；仅清除失败/跳过残留
        self.clear(todo_id)

    def get_status(self, todo_id: str) -> str:
        return self._status_map.get(todo_id, "")

    def get_tooltip(self, todo_id: str) -> str:
        return self._tooltips_map.get(todo_id, "")


