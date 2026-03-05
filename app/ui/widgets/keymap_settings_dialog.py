from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.keymap_store import KeymapActionSpec, KeymapStore
from app.ui.foundation.theme_manager import Sizes, ThemeManager
from app.ui.foundation import dialog_utils


@dataclass
class _KeymapRow:
    spec: KeymapActionSpec
    shortcut_edits: list[QtWidgets.QKeySequenceEdit]
    row_index: int

    def search_text(self) -> str:
        parts = [self.spec.scope, self.spec.title, self.spec.description]
        return "\n".join([str(p or "") for p in parts]).lower()


class KeymapSettingsDialog(BaseDialog):
    """快捷键设置：编辑并保存 KeymapStore 的快捷键覆盖配置。"""

    def __init__(self, keymap_store: KeymapStore, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            title="快捷键设置",
            width=920,
            height=680,
            use_scroll=False,
            parent=parent,
        )
        self._keymap_store = keymap_store
        self._rows: list[_KeymapRow] = []
        self._row_search_cache: list[str] = []

        self.setObjectName("keymapSettingsDialog")
        self._build_ui()
        self._populate_table()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Sizes.SPACING_MEDIUM)

        # 顶部操作行：搜索 + 恢复默认
        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(Sizes.SPACING_MEDIUM)

        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索快捷键（例如：验证 / 新建 / Ctrl+N / 画布搜索 …）")
        self.search_edit.setMinimumHeight(Sizes.INPUT_HEIGHT + 2)
        self.search_edit.textChanged.connect(self._apply_filter)
        top_row.addWidget(self.search_edit, 1)

        self.reset_button = QtWidgets.QPushButton("恢复默认", self)
        self.reset_button.setToolTip("将所有快捷键恢复为默认配置（需点击“确定”保存）。")
        self.reset_button.clicked.connect(self._reset_all_to_defaults)
        top_row.addWidget(self.reset_button)

        root.addLayout(top_row)

        # 表格
        self.table = QtWidgets.QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["作用域", "操作", "快捷键", "说明"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet(ThemeManager.table_style())
        root.addWidget(self.table, 1)

        hint = QtWidgets.QLabel(
            "提示：点击快捷键输入框后直接按下组合键即可录入；按 Backspace 可清空当前输入框。", self
        )
        hint.setStyleSheet(ThemeManager.hint_text_style())
        root.addWidget(hint)

        self.add_layout(root)

    def _populate_table(self) -> None:
        specs = list(self._keymap_store.list_default_specs())

        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(specs))
            self._rows = []

            for row_index, spec in enumerate(specs):
                self.table.setItem(row_index, 0, QtWidgets.QTableWidgetItem(spec.scope))
                self.table.setItem(row_index, 1, QtWidgets.QTableWidgetItem(spec.title))
                self.table.setItem(row_index, 3, QtWidgets.QTableWidgetItem(spec.description))

                current_shortcuts = self._keymap_store.get_shortcuts(spec.action_id)
                cell_widget = QtWidgets.QWidget(self.table)
                cell_layout = QtWidgets.QHBoxLayout(cell_widget)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setSpacing(6)

                edits: list[QtWidgets.QKeySequenceEdit] = []
                for i in range(max(1, int(spec.max_shortcuts))):
                    edit = QtWidgets.QKeySequenceEdit(cell_widget)
                    edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
                    if i < len(current_shortcuts):
                        edit.setKeySequence(QtGui.QKeySequence(current_shortcuts[i]))
                    edits.append(edit)
                    cell_layout.addWidget(edit, 1)

                self.table.setCellWidget(row_index, 2, cell_widget)
                self._rows.append(_KeymapRow(spec=spec, shortcut_edits=edits, row_index=row_index))

            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        finally:
            self.table.setUpdatesEnabled(True)

        self._row_search_cache = [row.search_text() for row in self._rows]

    def _reset_all_to_defaults(self) -> None:
        for row in self._rows:
            defaults = self._keymap_store.get_default_shortcuts(row.spec.action_id)
            for i, edit in enumerate(row.shortcut_edits):
                if i < len(defaults):
                    edit.setKeySequence(QtGui.QKeySequence(defaults[i]))
                else:
                    edit.setKeySequence(QtGui.QKeySequence())

    def _apply_filter(self, text: str) -> None:
        query = str(text or "").strip().lower()
        if not query:
            for row in self._rows:
                self.table.setRowHidden(row.row_index, False)
            return

        for row, search_text in zip(self._rows, self._row_search_cache):
            self.table.setRowHidden(row.row_index, query not in search_text)

    # ------------------------------------------------------------------ Save / Validate
    def _collect_shortcuts(self, row: _KeymapRow) -> list[str]:
        values: list[str] = []
        for edit in row.shortcut_edits:
            seq = edit.keySequence()
            text = str(seq.toString() or "").strip()
            if text:
                values.append(text)
        return values

    def validate(self) -> bool:
        # 1) 收集并做冲突提示（允许用户继续保存）
        reverse_index: dict[str, list[str]] = {}
        for row in self._rows:
            shortcuts = self._collect_shortcuts(row)
            for shortcut in shortcuts:
                reverse_index.setdefault(shortcut, []).append(row.spec.title)

        conflicts = {k: v for k, v in reverse_index.items() if len(v) > 1}
        if conflicts:
            lines: list[str] = ["检测到快捷键冲突（同一组合键绑定了多个动作）：", ""]
            for shortcut, titles in sorted(conflicts.items(), key=lambda kv: kv[0].lower()):
                joined = "、".join(titles[:6])
                suffix = "…" if len(titles) > 6 else ""
                lines.append(f"- {shortcut}: {joined}{suffix}")
            lines.append("")
            lines.append("是否仍要保存？（冲突可能导致触发不确定或被更上层快捷键拦截）")

            should_continue = dialog_utils.ask_yes_no_dialog(
                self,
                "快捷键冲突",
                "\n".join(lines),
                default_yes=False,
            )
            if not should_continue:
                return False

        # 2) 写回到 KeymapStore，并保存到 runtime cache
        for row in self._rows:
            self._keymap_store.set_shortcuts(row.spec.action_id, self._collect_shortcuts(row))

        self._keymap_store.save()
        return True


__all__ = ["KeymapSettingsDialog"]


