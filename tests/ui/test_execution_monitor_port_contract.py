from __future__ import annotations

from PyQt6 import QtWidgets

from app.ui.execution.monitor.panel import ExecutionMonitorPanel
from app.ui.todo.todo_ports import ExecutionMonitorPort


def _ensure_qt_app() -> QtWidgets.QApplication:
    app_instance = QtWidgets.QApplication.instance()
    if app_instance is None:
        app_instance = QtWidgets.QApplication([])
    return app_instance


def test_execution_monitor_panel_implements_todo_execution_monitor_port() -> None:
    _ensure_qt_app()
    panel = ExecutionMonitorPanel()
    assert isinstance(panel, ExecutionMonitorPort)


