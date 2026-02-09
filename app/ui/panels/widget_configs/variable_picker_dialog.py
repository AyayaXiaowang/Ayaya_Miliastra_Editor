from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import ThemeManager

__all__ = ["VariablePickerDialog"]


class VariablePickerDialog(BaseDialog):
    """变量选择器（带搜索）。"""

    def __init__(
        self,
        available_variables: Dict[str, Dict[str, Any]],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(
            title="变量库",
            width=680,
            height=520,
            use_scroll=False,
            parent=parent,
        )
        self._available_variables = available_variables
        self._selected_variable_name: str = ""

        self._build_ui()
        self._populate()
        self._apply_filter("")

    def get_selected_variable_name(self) -> str:
        return self._selected_variable_name

    # ----------------------------------------------------------------------------------
    # UI
    # ----------------------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("搜索变量…")
        self.search_edit.setStyleSheet(ThemeManager.input_style())
        self.search_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_edit)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _: self._try_accept())
        layout.addWidget(self.list_widget, 1)

        container = QtWidgets.QWidget()
        container.setLayout(layout)
        self.add_widget(container)

        ok_btn = self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setEnabled(False)

    def _populate(self) -> None:
        items: list[tuple[str, str]] = []
        for _, payload in self._available_variables.items():
            if not isinstance(payload, dict):
                continue
            name_text = str(payload.get("variable_name") or payload.get("name") or "").strip()
            if not name_text:
                continue
            type_text = str(payload.get("variable_type") or "").strip()
            source_stem = str(payload.get("source_stem") or "").strip()
            file_display = source_stem or str(payload.get("source_file") or "").strip() or "<unknown>"
            display = f"{name_text} | {type_text} | {file_display}" if type_text else f"{name_text} | {file_display}"
            items.append((name_text, display))

        items.sort(key=lambda pair: pair[0].casefold())
        self.list_widget.clear()
        for variable_name, display in items:
            item = QtWidgets.QListWidgetItem(display)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, variable_name)
            self.list_widget.addItem(item)

    # ----------------------------------------------------------------------------------
    # Filtering / selection
    # ----------------------------------------------------------------------------------
    def _apply_filter(self, text: str) -> None:
        query = str(text or "").strip().casefold()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item is None:
                continue
            visible = True
            if query:
                visible = query in item.text().casefold()
            item.setHidden(not visible)

    def _on_selection_changed(self) -> None:
        selected_items = self.list_widget.selectedItems()
        self._selected_variable_name = ""
        if selected_items:
            raw = selected_items[0].data(QtCore.Qt.ItemDataRole.UserRole)
            self._selected_variable_name = str(raw or "").strip()

        ok_btn = self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setEnabled(bool(self._selected_variable_name))

    def _try_accept(self) -> None:
        if not self._selected_variable_name:
            return
        self.accept()

    def validate(self) -> bool:
        return bool(self._selected_variable_name)



