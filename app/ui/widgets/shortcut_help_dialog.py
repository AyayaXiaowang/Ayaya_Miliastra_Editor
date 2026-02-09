from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import Sizes, ThemeManager


@dataclass(frozen=True)
class ShortcutHelpItem:
    """一条快捷键说明。"""

    scope: str
    action: str
    shortcut: str
    description: str

    def search_text(self) -> str:
        return f"{self.scope}\n{self.action}\n{self.shortcut}\n{self.description}".lower()


class ShortcutHelpDialog(BaseDialog):
    """快捷键面板：展示当前程序的主要快捷键，并支持搜索过滤。"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            title="快捷键面板",
            width=880,
            height=620,
            use_scroll=False,
            buttons=QtWidgets.QDialogButtonBox.StandardButton.NoButton,
            parent=parent,
        )
        self.setObjectName("shortcutHelpDialog")

        # BaseDialog 默认会创建 button_box；快捷键面板不需要底部按钮区。
        if hasattr(self, "button_box") and self.button_box is not None:
            self.button_box.hide()

        self._all_items: list[ShortcutHelpItem] = []
        self._search_cache: list[str] = []

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_MEDIUM)

        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索快捷键（例如：复制 / Ctrl+D / 验证 / 存档 …）")
        self.search_edit.setMinimumHeight(Sizes.INPUT_HEIGHT + 2)
        self.search_edit.textChanged.connect(self._apply_filter)

        settings_btn = QtWidgets.QPushButton("快捷键设置…", self)
        settings_btn.setToolTip("自定义并保存快捷键绑定")
        settings_btn.clicked.connect(self._open_keymap_settings_dialog)

        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(Sizes.SPACING_SMALL)
        top_row.addWidget(self.search_edit, 1)
        top_row.addWidget(settings_btn)

        self.table = QtWidgets.QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["作用域", "操作", "快捷键", "说明"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet(ThemeManager.table_style())

        hint_label = QtWidgets.QLabel("提示：可在“快捷键设置”中自定义快捷键；命令面板也可搜索“快捷键设置”。", self)
        hint_label.setStyleSheet(ThemeManager.hint_text_style())

        layout.addLayout(top_row)
        layout.addWidget(self.table, 1)
        layout.addWidget(hint_label)
        self.add_layout(layout)

    def set_items(self, items: Iterable[ShortcutHelpItem]) -> None:
        self._all_items = list(items or [])
        self._search_cache = [item.search_text() for item in self._all_items]
        self._rebuild_table(self._all_items)

    # ------------------------------------------------------------------ 交互

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ 搜索过滤

    def _apply_filter(self, text: str) -> None:
        query = str(text or "").strip().lower()
        if not query:
            self._rebuild_table(self._all_items)
            return

        matched: list[ShortcutHelpItem] = []
        for item, search_text in zip(self._all_items, self._search_cache):
            if query in search_text:
                matched.append(item)
        self._rebuild_table(matched)

    def _rebuild_table(self, items: list[ShortcutHelpItem]) -> None:
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(items))
            for row_index, item in enumerate(items):
                self.table.setItem(row_index, 0, QtWidgets.QTableWidgetItem(item.scope))
                self.table.setItem(row_index, 1, QtWidgets.QTableWidgetItem(item.action))
                self.table.setItem(row_index, 2, QtWidgets.QTableWidgetItem(item.shortcut))
                self.table.setItem(row_index, 3, QtWidgets.QTableWidgetItem(item.description))

            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        finally:
            self.table.setUpdatesEnabled(True)

    def _open_keymap_settings_dialog(self) -> None:
        parent = self.parent()
        open_dialog = getattr(parent, "_open_keymap_settings_dialog", None) if parent is not None else None
        if callable(open_dialog):
            open_dialog()
        rebuild = getattr(parent, "_build_shortcut_help_items", None) if parent is not None else None
        if callable(rebuild):
            self.set_items(rebuild())


__all__ = ["ShortcutHelpDialog", "ShortcutHelpItem"]


