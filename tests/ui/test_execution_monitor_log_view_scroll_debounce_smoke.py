from __future__ import annotations

from PyQt6 import QtWidgets

from app.ui.execution.monitor.log_view import LogViewController


_app = QtWidgets.QApplication.instance()
if _app is None:
    _app = QtWidgets.QApplication([])


def test_log_view_append_many_lines_does_not_crash_and_renders() -> None:
    log_text = QtWidgets.QTextBrowser()
    search_input = QtWidgets.QLineEdit()
    filter_combo = QtWidgets.QComboBox()
    filter_combo.addItems(["全部", "仅等待"])

    controller = LogViewController(
        log_text_browser=log_text,
        search_input=search_input,
        filter_combo=filter_combo,
    )

    for index in range(200):
        controller.append(f"等待 0.{index%10}0 秒...")

    # 触发 singleShot(0) 的滚动任务
    QtWidgets.QApplication.processEvents()

    html = log_text.toHtml()
    assert "等待" in html


