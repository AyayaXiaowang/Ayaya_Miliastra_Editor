from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.theme_manager import ThemeManager, Colors, Sizes
from app.ui.foundation.performance_monitor import AppPerformanceMonitor, UiStallEvent


class AppPerformanceOverlay(QtWidgets.QFrame):
    """主窗口级性能悬浮面板（全页面可见）。"""

    requested_open_details = QtCore.pyqtSignal()

    _TIMER_INTERVAL_MS: int = 200

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        *,
        monitor: AppPerformanceMonitor,
    ) -> None:
        super().__init__(parent)
        self._monitor = monitor
        self.setObjectName("appPerfOverlay")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.setStyleSheet(
            ThemeManager.graph_search_overlay_style()
            + f"""
            QFrame#appPerfOverlay {{
                background-color: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER_LIGHT};
                border-radius: {Sizes.RADIUS_MEDIUM}px;
            }}
            QLabel#appPerfText {{
                color: {Colors.TEXT_PRIMARY};
            }}
            """
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        self._label = QtWidgets.QLabel("", self)
        self._label.setObjectName("appPerfText")
        self._label.setFont(ui_fonts.monospace_font(9))
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._label.setCursor(Qt.CursorShape.IBeamCursor)
        self._label.setWordWrap(False)
        layout.addWidget(self._label)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(int(self._TIMER_INTERVAL_MS))
        self._timer.timeout.connect(self._refresh)

        self.hide()

    def start(self) -> None:
        self._timer.start()
        self._refresh()
        self.reposition()
        self.show()
        self.raise_()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.requested_open_details.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[override]
        event.ignore()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        geom = parent.rect()
        if geom.isNull():
            return

        margin = 12
        width = 420
        height = 84

        x = int(geom.width() - width - margin)
        y = int(margin)
        if x < margin:
            x = int(margin)
        self.setGeometry(x, y, int(width), int(height))

    def _refresh(self) -> None:
        snap = self._monitor.get_snapshot()
        enabled = bool(snap.get("enabled"))
        gap_ms = float(snap.get("heartbeat_gap_ms") or 0.0)
        threshold_ms = float(snap.get("stall_threshold_ms") or 0.0)
        stalls = list(snap.get("stall_events") or [])
        spans = list(snap.get("span_events") or [])

        last_stall_ms = 0.0
        last_stall_top = ""
        if stalls:
            last_ev: UiStallEvent = stalls[-1]
            last_stall_ms = float(last_ev.duration_ms)
            last_stall_top = str(last_ev.top_frame or "").strip()

        status = "ON" if enabled else "OFF"
        lines = [
            f"Perf Monitor: {status}",
            f"UI gap: {gap_ms:.1f}ms  (stall>={threshold_ms:.0f}ms)",
            f"stalls: {len(stalls)}  spans: {len(spans)}  last_stall: {last_stall_ms:.1f}ms",
        ]
        if last_stall_top:
            trimmed = last_stall_top
            if len(trimmed) > 80:
                trimmed = trimmed[:80] + "..."
            lines.append(trimmed)

        text = "\n".join(lines)
        if self._label.text() != text:
            self._label.setText(text)
        self.reposition()

