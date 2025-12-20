from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from app.ui.execution.monitor import panel_ui


_app = QtWidgets.QApplication.instance()
if _app is None:
    _app = QtWidgets.QApplication([])


def test_build_monitor_ui_does_not_warn_splitter_setcollapsible_out_of_range() -> None:
    captured_messages: list[str] = []

    def _qt_message_handler(_msg_type, _context, message: str) -> None:
        captured_messages.append(str(message))

    previous_handler = QtCore.qInstallMessageHandler(_qt_message_handler)
    try:
        parent = QtWidgets.QWidget()
        refs = panel_ui.build_monitor_ui(parent)
        assert isinstance(refs, dict)
    finally:
        QtCore.qInstallMessageHandler(previous_handler)

    out_of_range = [m for m in captured_messages if "QSplitter::setCollapsible: Index" in m]
    assert out_of_range == []


