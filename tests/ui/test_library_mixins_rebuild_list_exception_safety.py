from __future__ import annotations

import pytest
from PyQt6 import QtWidgets

from app.ui.graph.library_mixins import rebuild_list_with_preserved_selection


_app = QtWidgets.QApplication.instance()
if _app is None:
    _app = QtWidgets.QApplication([])


def test_rebuild_list_with_preserved_selection_restores_widget_state_on_exception() -> None:
    list_widget = QtWidgets.QListWidget()
    list_widget.setUpdatesEnabled(True)

    def build_items_raises() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        rebuild_list_with_preserved_selection(
            list_widget,
            previous_key=None,
            had_selection_before_refresh=False,
            build_items=build_items_raises,
            key_getter=lambda _item: None,
        )

    # 关键：异常不能把控件永久留在“禁用更新/阻塞信号”的状态，否则 UI 会表现为假死
    assert list_widget.updatesEnabled() is True
    assert list_widget.signalsBlocked() is False

    def build_items_ok() -> None:
        list_widget.addItem(QtWidgets.QListWidgetItem("hello"))

    rebuild_list_with_preserved_selection(
        list_widget,
        previous_key=None,
        had_selection_before_refresh=False,
        build_items=build_items_ok,
        key_getter=lambda item: item.text(),
    )

    assert list_widget.count() == 1
    first_item = list_widget.item(0)
    assert first_item is not None
    assert first_item.text() == "hello"
    assert list_widget.updatesEnabled() is True
    assert list_widget.signalsBlocked() is False


