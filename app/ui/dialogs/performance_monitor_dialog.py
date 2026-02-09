from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import ThemeManager, Colors, Sizes
from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.performance_monitor import AppPerformanceMonitor


class PerformanceMonitorDialog(BaseDialog):
    """全局性能监控面板（非模态，可在所有页面保持打开）。"""

    _REFRESH_INTERVAL_MS: int = 250

    def __init__(
        self,
        *,
        monitor: AppPerformanceMonitor,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            title="性能监控",
            width=960,
            height=680,
            use_scroll=False,
            buttons=QtWidgets.QDialogButtonBox.StandardButton.Close,
            parent=parent,
        )
        self.setModal(False)
        self._monitor = monitor

        self._last_report_key: tuple = ()

        self._build_ui()
        self._apply_styles()
        self._start_timer()

    def _apply_styles(self) -> None:
        base_style = (
            ThemeManager.dialog_surface_style(include_tables=False)
            + ThemeManager.scrollbar_style()
            + ThemeManager.group_box_style()
        )
        self.setStyleSheet(base_style)

    def _build_ui(self) -> None:
        header = QtWidgets.QWidget(self.content_widget)
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(Sizes.SPACING_MEDIUM)

        self._status_label = QtWidgets.QLabel("监控未启用", header)
        status_font = self._status_label.font()
        status_font.setBold(True)
        self._status_label.setFont(status_font)
        header_layout.addWidget(self._status_label, 1)

        self._copy_button = QtWidgets.QPushButton("一键复制", header)
        self._copy_button.setToolTip("复制当前性能报告到剪贴板")
        self._copy_button.clicked.connect(self._copy_report)
        header_layout.addWidget(self._copy_button)

        self._clear_button = QtWidgets.QPushButton("清空记录", header)
        self._clear_button.setToolTip("清空已记录的卡顿事件与耗时段")
        self._clear_button.clicked.connect(self._clear_events)
        header_layout.addWidget(self._clear_button)

        self.content_layout.addWidget(header)

        self._text = QtWidgets.QPlainTextEdit(self.content_widget)
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self._text.setFont(ui_fonts.monospace_font(9))
        self._text.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._text.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {Colors.BG_CARD}; border: 1px solid {Colors.BORDER_LIGHT}; }}"
        )
        self.content_layout.addWidget(self._text, 1)

        hint = QtWidgets.QLabel(
            "提示：此面板主要用于定位“UI线程卡顿”。当页面卡住时，它会记录卡顿时刻的主线程调用栈（若已开启）。",
            self.content_widget,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(ThemeManager.hint_text_style())
        self.content_layout.addWidget(hint)

    def _start_timer(self) -> None:
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(int(self._REFRESH_INTERVAL_MS))
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        timer = getattr(self, "_timer", None)
        if isinstance(timer, QtCore.QTimer):
            timer.stop()
        super().closeEvent(event)

    def _refresh(self) -> None:
        snap = self._monitor.get_snapshot()
        enabled = bool(snap.get("enabled"))
        gap_ms = float(snap.get("heartbeat_gap_ms") or 0.0)
        avg_ms = float(snap.get("heartbeat_interval_avg_ms") or 0.0)
        max_ms = float(snap.get("heartbeat_interval_max_ms") or 0.0)
        threshold_ms = float(snap.get("stall_threshold_ms") or 0.0)
        capture_stacks = bool(snap.get("capture_stacks"))
        stalls = list(snap.get("stall_events") or [])
        spans = list(snap.get("span_events") or [])
        event_seq = int(snap.get("event_seq") or 0)

        if enabled:
            self._status_label.setText(
                f"监控已启用  |  UI gap={gap_ms:.1f}ms (avg={avg_ms:.1f}ms, max={max_ms:.1f}ms)  |  "
                f"stall>={threshold_ms:.0f}ms  |  stalls={len(stalls)} spans={len(spans)}"
            )
        else:
            self._status_label.setText("监控未启用（可在设置→性能中开启）")

        report_key = (event_seq, enabled, float(threshold_ms), bool(capture_stacks))
        if report_key != self._last_report_key:
            self._last_report_key = report_key
            # 事件文本只在 stall/span 变化时刷新，避免高频 setPlainText 反过来制造卡顿。
            report = self._monitor.format_report_text(include_live_metrics=False)
            if self._text.toPlainText() != report:
                self._text.setPlainText(report)

    def _copy_report(self) -> None:
        cb = QtWidgets.QApplication.clipboard()
        if cb is None:
            return
        # 复制时附带实时指标（gap/avg/max），便于离线排查。
        cb.setText(self._monitor.format_report_text(include_live_metrics=True))
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "已复制")

    def _clear_events(self) -> None:
        was_enabled = bool(self._monitor.is_enabled())
        self._monitor.clear_events()
        # 清空不应导致后续“再也没有卡顿记录”的错觉：
        # - 若 watchdog 线程曾异常退出，monitor 可能处于 enabled=True 但不再产出事件的僵尸态；
        # - start() 为幂等且自愈：enabled=True 时也会确保心跳与 watchdog 处于运行态。
        if was_enabled:
            self._monitor.start()
        self._refresh()

