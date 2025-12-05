from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

from ui.foundation.theme_manager import Colors


@dataclass
class ExecutionEvent:
    """结构化执行事件：用于在监控面板中表格展示一次运行的关键节点。"""

    timestamp: datetime
    run_id: str
    kind: str  # "run" / "step"
    phase: str  # "start" / "success" / "fail" / "skip"
    severity: str  # "info" / "warning" / "error"
    message: str
    todo_id: Optional[str] = None
    todo_title: Optional[str] = None
    step_index: Optional[int] = None  # 从 0 开始
    total_steps: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def short_time(self) -> str:
        return self.timestamp.strftime("%H:%M:%S")


class ExecutionEventModel(QtCore.QAbstractTableModel):
    """
    执行事件表格模型：
    - 行：ExecutionEvent
    - 列：时间 / 类型 / 状态 / 步骤 / 描述
    - 默认仅显示当前运行的事件，可选仅显示错误/警告。
    """

    COL_TIME = 0
    COL_KIND = 1
    COL_STATUS = 2
    COL_STEP = 3
    COL_MESSAGE = 4

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._events: List[ExecutionEvent] = []
        self._run_counter: int = 0
        self._current_run_id: Optional[str] = None
        self._only_current_run: bool = True
        self._only_errors: bool = False

    # === 运行控制 ===

    @property
    def current_run_id(self) -> Optional[str]:
        return self._current_run_id

    def clear(self) -> None:
        """清空所有事件（通常在彻底重置监控时调用）。"""
        self.beginResetModel()
        self._events.clear()
        self._current_run_id = None
        self.endResetModel()

    def start_new_run(self, total_steps: int = 0) -> str:
        """开始一次新的运行，返回 run_id。"""
        self._run_counter += 1
        run_id = f"run-{self._run_counter}"
        self._current_run_id = run_id

        msg = "开始执行"
        if total_steps > 0:
            msg = f"开始执行（共 {total_steps} 步）"

        event = ExecutionEvent(
            timestamp=datetime.now(),
            run_id=run_id,
            kind="run",
            phase="start",
            severity="info",
            message=msg,
            total_steps=total_steps or None,
        )
        self.beginResetModel()
        self._events.append(event)
        self.endResetModel()
        return run_id

    def finish_run(self, success: bool, reason: Optional[str] = None) -> None:
        """结束当前运行，记录运行结果。"""
        if not self._current_run_id:
            return
        base = "执行完成" if success else "执行结束（含失败）"
        if reason:
            msg = f"{base}：{reason}"
        else:
            msg = base
        event = ExecutionEvent(
            timestamp=datetime.now(),
            run_id=self._current_run_id,
            kind="run",
            phase="success" if success else "fail",
            severity="info" if success else "error",
            message=msg,
        )
        self.beginResetModel()
        self._events.append(event)
        self.endResetModel()

    # === 步骤事件 ===

    def add_step_started(
        self,
        todo_id: str,
        todo_title: str,
        step_index: Optional[int],
        total_steps: Optional[int],
    ) -> None:
        if not self._current_run_id:
            return
        idx = (step_index or 0) + 1
        msg_prefix = f"[{idx}/{total_steps}]" if total_steps and total_steps > 0 else ""
        label = todo_title or todo_id or ""
        pieces = [p for p in (msg_prefix, f"开始步骤：{label}") if p]
        msg = " ".join(pieces)
        event = ExecutionEvent(
            timestamp=datetime.now(),
            run_id=self._current_run_id,
            kind="step",
            phase="start",
            severity="info",
            message=msg,
            todo_id=todo_id or None,
            todo_title=todo_title or None,
            step_index=step_index,
            total_steps=total_steps,
        )
        self._append_event(event)

    def add_step_completed(
        self,
        todo_id: str,
        todo_title: str,
        step_index: Optional[int],
        total_steps: Optional[int],
        success: bool,
        reason: Optional[str] = None,
    ) -> None:
        if not self._current_run_id:
            return
        idx = (step_index or 0) + 1
        label = todo_title or todo_id or ""
        status_text = "步骤成功" if success else "步骤失败"
        msg_parts: List[str] = []
        if total_steps and total_steps > 0:
            msg_parts.append(f"[{idx}/{total_steps}]")
        msg_parts.append(f"{status_text}：{label}")
        if reason:
            msg_parts.append(f"（{reason}）")
        msg = " ".join(msg_parts)
        event = ExecutionEvent(
            timestamp=datetime.now(),
            run_id=self._current_run_id,
            kind="step",
            phase="success" if success else "fail",
            severity="info" if success else "error",
            message=msg,
            todo_id=todo_id or None,
            todo_title=todo_title or None,
            step_index=step_index,
            total_steps=total_steps,
        )
        self._append_event(event)

    def add_step_skipped(
        self,
        todo_id: str,
        todo_title: str,
        step_index: Optional[int],
        total_steps: Optional[int],
        reason: str,
    ) -> None:
        if not self._current_run_id:
            return
        idx = (step_index or 0) + 1
        label = todo_title or todo_id or ""
        msg_parts: List[str] = []
        if total_steps and total_steps > 0:
            msg_parts.append(f"[{idx}/{total_steps}]")
        msg_parts.append(f"步骤被跳过：{label}")
        if reason:
            msg_parts.append(f"（{reason}）")
        msg = " ".join(msg_parts)
        event = ExecutionEvent(
            timestamp=datetime.now(),
            run_id=self._current_run_id,
            kind="step",
            phase="skip",
            severity="warning",
            message=msg,
            todo_id=todo_id or None,
            todo_title=todo_title or None,
            step_index=step_index,
            total_steps=total_steps,
        )
        self._append_event(event)

    def _append_event(self, event: ExecutionEvent) -> None:
        """内部统一追加事件并刷新视图。"""
        self.beginResetModel()
        self._events.append(event)
        self.endResetModel()

    # === 过滤控制 ===

    def set_only_current_run(self, value: bool) -> None:
        value = bool(value)
        if self._only_current_run != value:
            self._only_current_run = value
            self._emit_reset()

    def set_only_errors(self, value: bool) -> None:
        value = bool(value)
        if self._only_errors != value:
            self._only_errors = value
            self._emit_reset()

    def _emit_reset(self) -> None:
        self.beginResetModel()
        self.endResetModel()

    def _filtered_events(self) -> List[ExecutionEvent]:
        events = self._events
        if self._only_current_run and self._current_run_id:
            events = [e for e in events if e.run_id == self._current_run_id]
        if self._only_errors:
            events = [e for e in events if e.severity in ("warning", "error")]
        return events

    # === QAbstractTableModel 接口 ===

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # type: ignore[override]
        if parent.isValid():
            return 0
        return len(self._filtered_events())

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # type: ignore[override]
        if parent.isValid():
            return 0
        return 5

    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:  # type: ignore[override]
        if not index.isValid():
            return None
        events = self._filtered_events()
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(events):
            return None
        event = events[row]

        # PyQt6 使用 ItemDataRole 枚举来区分不同的数据角色
        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.COL_TIME:
                return event.short_time
            if col == self.COL_KIND:
                return "运行" if event.kind == "run" else "步骤"
            if col == self.COL_STATUS:
                if event.kind == "run":
                    if event.phase == "start":
                        return "开始"
                    if event.phase == "success":
                        return "完成"
                    if event.phase == "fail":
                        return "失败"
                    return ""
                if event.kind == "step":
                    if event.phase == "start":
                        return "执行中"
                    if event.phase == "success":
                        return "成功"
                    if event.phase == "fail":
                        return "失败"
                    if event.phase == "skip":
                        return "跳过"
                    return ""
            if col == self.COL_STEP:
                if event.todo_title:
                    if event.step_index is not None and event.total_steps:
                        return f"{event.todo_title} [{event.step_index + 1}/{event.total_steps}]"
                    return event.todo_title
                return event.todo_id or ""
            if col == self.COL_MESSAGE:
                return event.message
            return ""

        if role == Qt.ItemDataRole.ToolTipRole:
            return event.message

        if role == Qt.ItemDataRole.ForegroundRole:
            # 错误/警告高亮，默认采用主题主文本色
            if event.severity == "error":
                return QtGui.QBrush(QtGui.QColor(Colors.ERROR))
            if event.severity == "warning":
                return QtGui.QBrush(QtGui.QColor(Colors.WARNING))
            return QtGui.QBrush(QtGui.QColor(Colors.TEXT_PRIMARY))

        if role == Qt.ItemDataRole.BackgroundRole:
            # 运行级事件淡背景
            if event.kind == "run":
                return QtGui.QBrush(QtGui.QColor(Colors.BG_MAIN))
            # 失败步骤浅红底
            if event.kind == "step" and event.phase == "fail":
                return QtGui.QBrush(QtGui.QColor(Colors.ERROR_BG))
            # 跳过步骤浅黄底
            if event.kind == "step" and event.phase == "skip":
                return QtGui.QBrush(QtGui.QColor(Colors.WARNING_BG))
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (self.COL_TIME, self.COL_KIND, self.COL_STATUS):
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:  # type: ignore[override]
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        if section == self.COL_TIME:
            return "时间"
        if section == self.COL_KIND:
            return "类型"
        if section == self.COL_STATUS:
            return "状态"
        if section == self.COL_STEP:
            return "步骤"
        if section == self.COL_MESSAGE:
            return "描述"
        return ""

    # === 便利方法 ===

    def get_event_at(self, row: int) -> Optional[ExecutionEvent]:
        events = self._filtered_events()
        if row < 0 or row >= len(events):
            return None
        return events[row]



