"""通用的表格 + CRUD 工具栏组件。"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Sequence

from PyQt6 import QtWidgets

from app.ui.graph.library_mixins import SearchFilterMixin, ToolbarMixin


class BaseCrudTableWidget(QtWidgets.QWidget, SearchFilterMixin, ToolbarMixin):
    """为“工具栏 + 搜索 + 表格”模式提供统一的脚手架。"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._toolbar_buttons: Dict[str, QtWidgets.QAbstractButton] = {}
        self.search_edit: Optional[QtWidgets.QLineEdit] = None

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

    def build_toolbar(
        self,
        buttons: Sequence[tuple[str, str, Callable[[], None]]],
        search_placeholder: str,
        on_search_text_changed: Callable[[str], None],
    ) -> None:
        """创建标准化的 CRUD 工具栏并连接搜索框。"""
        toolbar_layout = QtWidgets.QHBoxLayout()
        self.init_toolbar(toolbar_layout)

        button_widgets: list[QtWidgets.QAbstractButton] = []
        for text, key, handler in buttons:
            button = QtWidgets.QPushButton(text, self)
            button.clicked.connect(handler)
            self._toolbar_buttons[key] = button
            button_widgets.append(button)

        search_edit = QtWidgets.QLineEdit(self)
        self.connect_search(search_edit, on_search_text_changed, search_placeholder)
        self.search_edit = search_edit

        self.setup_toolbar_with_search(toolbar_layout, button_widgets, search_edit)
        self.main_layout.addLayout(toolbar_layout)

    def set_controls_enabled(
        self,
        enabled: bool,
        extra_widgets: Sequence[QtWidgets.QWidget] = (),
    ) -> None:
        """统一开启/禁用工具栏按钮、搜索输入与额外控件。"""
        for button in self._toolbar_buttons.values():
            button.setEnabled(enabled)
        if self.search_edit:
            self.search_edit.setEnabled(enabled)
        for widget in extra_widgets:
            widget.setEnabled(enabled)

    def toolbar_button(self, key: str) -> QtWidgets.QAbstractButton:
        """按 key 获取工具栏按钮实例。"""
        return self._toolbar_buttons[key]


__all__ = ["BaseCrudTableWidget"]

