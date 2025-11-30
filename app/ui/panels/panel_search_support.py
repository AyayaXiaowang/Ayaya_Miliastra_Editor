from __future__ import annotations

from typing import Callable, Optional

from PyQt6 import QtCore, QtWidgets


class SidebarSearchController(QtCore.QObject):
    """统一的侧边搜索输入控制器，负责去抖与空白裁剪。"""

    def __init__(
        self,
        placeholder: str,
        on_text_changed: Callable[[str], None],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._normalized_text = ""
        self._on_text_changed = on_text_changed
        self._line_edit = QtWidgets.QLineEdit(parent)
        self._line_edit.setPlaceholderText(placeholder)
        self._line_edit.setClearButtonEnabled(True)
        self._line_edit.textChanged.connect(self._handle_text_changed)

    @property
    def widget(self) -> QtWidgets.QLineEdit:
        return self._line_edit

    @property
    def value(self) -> str:
        return self._normalized_text

    def set_text(self, text: str) -> None:
        if text == self._line_edit.text():
            return
        self._line_edit.setText(text)

    def _handle_text_changed(self, text: str) -> None:
        normalized = text.strip().casefold()
        if normalized == self._normalized_text:
            return
        self._normalized_text = normalized
        self._on_text_changed(normalized)

