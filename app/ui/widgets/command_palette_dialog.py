from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import Sizes, ThemeManager


@dataclass(frozen=True)
class CommandPaletteEntry:
    """命令面板中的一条可执行条目。"""

    title: str
    subtitle: str
    keywords: str
    action: Callable[[], None]

    def build_search_text(self) -> str:
        title_text = str(self.title or "")
        subtitle_text = str(self.subtitle or "")
        keywords_text = str(self.keywords or "")
        return f"{title_text}\n{subtitle_text}\n{keywords_text}".lower()


class CommandPaletteDialog(BaseDialog):
    """全局搜索/命令面板。

    交互约定：
    - 输入框实时过滤结果；
    - Enter / 双击：执行当前选中条目并关闭；
    - Esc：关闭。
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            title="全局搜索 / 命令面板",
            width=860,
            height=540,
            use_scroll=False,
            buttons=QtWidgets.QDialogButtonBox.StandardButton.NoButton,
            parent=parent,
        )
        self.setObjectName("commandPaletteDialog")

        # BaseDialog 默认会创建 button_box；命令面板不需要底部按钮区。
        if hasattr(self, "button_box") and self.button_box is not None:
            self.button_box.hide()

        self._all_entries: list[CommandPaletteEntry] = []
        self._filtered_entries: list[CommandPaletteEntry] = []
        self._search_cache: list[str] = []

        self._build_content()

    def _build_content(self) -> None:
        root_layout = QtWidgets.QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(Sizes.SPACING_MEDIUM)

        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("输入关键词：元件 / 实体摆放 / 战斗预设 / 节点图 / 管理项 …")
        self.search_edit.setMinimumHeight(Sizes.INPUT_HEIGHT + 2)
        self.search_edit.textChanged.connect(self._on_query_changed)
        self.search_edit.returnPressed.connect(self._accept_current)

        self.result_list = QtWidgets.QListWidget(self)
        self.result_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.result_list.setAlternatingRowColors(True)
        self.result_list.setUniformItemSizes(False)
        self.result_list.itemActivated.connect(lambda _item: self._accept_current())

        # 提示行（轻量，不抢眼）
        self.hint_label = QtWidgets.QLabel("Enter 跳转 / Esc 关闭 / ↑↓ 选择", self)
        self.hint_label.setStyleSheet(ThemeManager.hint_text_style())

        root_layout.addWidget(self.search_edit)
        root_layout.addWidget(self.result_list, 1)
        root_layout.addWidget(self.hint_label)

        self.add_layout(root_layout)

    def set_entries(self, entries: Iterable[CommandPaletteEntry]) -> None:
        self._all_entries = list(entries or [])
        self._search_cache = [entry.build_search_text() for entry in self._all_entries]
        self._apply_filter(query="")

    # --------------------------------------------------------------------- 交互

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key in (QtCore.Qt.Key.Key_Escape,):
            self.reject()
            return
        super().keyPressEvent(event)

    # --------------------------------------------------------------------- 过滤

    def _on_query_changed(self, text: str) -> None:
        query = str(text or "").strip()
        self._apply_filter(query=query)

    @staticmethod
    def _score_match(search_text: str, query: str) -> int:
        if not query:
            return 0
        if search_text.startswith(query):
            return 300
        # title 行命中更高
        first_line = search_text.split("\n", 1)[0]
        if first_line.startswith(query):
            return 260
        pos = search_text.find(query)
        if pos >= 0:
            # 越靠前越高
            return max(30, 220 - min(200, pos))
        return -1

    def _apply_filter(self, *, query: str) -> None:
        query_text = str(query or "").strip().lower()
        scored: list[tuple[int, int, CommandPaletteEntry]] = []

        for index, (entry, search_text) in enumerate(zip(self._all_entries, self._search_cache)):
            if not query_text:
                scored.append((0, index, entry))
                continue
            score = self._score_match(search_text, query_text)
            if score >= 0:
                scored.append((score, index, entry))

        scored.sort(key=lambda it: (-it[0], it[1]))
        # 保持列表长度可控，避免极大工程下卡顿
        self._filtered_entries = [entry for _score, _index, entry in scored[:300]]
        self._rebuild_result_list()

    def _rebuild_result_list(self) -> None:
        self.result_list.setUpdatesEnabled(False)
        try:
            self.result_list.clear()
            for entry in self._filtered_entries:
                item = QtWidgets.QListWidgetItem()
                title = str(entry.title or "").strip()
                subtitle = str(entry.subtitle or "").strip()
                if subtitle:
                    item.setText(f"{title}\n{subtitle}")
                else:
                    item.setText(title)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, entry)
                item.setToolTip(subtitle)
                self.result_list.addItem(item)
        finally:
            self.result_list.setUpdatesEnabled(True)

        if self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)

    def _accept_current(self) -> None:
        current_item = self.result_list.currentItem()
        if current_item is None:
            return
        entry_any = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(entry_any, CommandPaletteEntry):
            return
        entry: CommandPaletteEntry = entry_any

        action = entry.action
        self.accept()
        QtCore.QTimer.singleShot(0, action)


__all__ = ["CommandPaletteDialog", "CommandPaletteEntry"]


