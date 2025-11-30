from __future__ import annotations

from typing import Optional

from PyQt6 import QtWidgets

from ui.foundation.base_widgets import BaseDialog
from ui.foundation import dialog_utils
from ui.foundation.context_menu_builder import ContextMenuBuilder
from .base import BaseWidgetConfigPanel, WidgetConfigForm


class CardSelectorConfigPanel(BaseWidgetConfigPanel):
    """卡牌选择器配置面板"""

    def _setup_ui(self) -> None:
        self._cards: list[dict[str, str]] = []
        layout = QtWidgets.QVBoxLayout(self)
        form = WidgetConfigForm(self)
        layout.addWidget(form)

        self.selection_mode_combo = form.add_combo_box(
            "选择模式:",
            "selection_mode",
            ["单选", "多选"],
            default_text="单选",
        )

        cards_group = QtWidgets.QGroupBox("卡牌列表")
        cards_layout = QtWidgets.QVBoxLayout(cards_group)
        self.cards_list = QtWidgets.QListWidget()
        self.cards_list.setMaximumHeight(150)
        self.cards_list.setContextMenuPolicy(
            QtWidgets.Qt.ContextMenuPolicy.CustomContextMenu  # type: ignore[attr-defined]
        )
        self.cards_list.customContextMenuRequested.connect(
            self._on_cards_context_menu
        )
        cards_layout.addWidget(self.cards_list)

        card_toolbar = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("添加卡牌")
        add_btn.clicked.connect(self._add_card)
        edit_btn = QtWidgets.QPushButton("编辑")
        edit_btn.clicked.connect(self._edit_card)
        remove_btn = QtWidgets.QPushButton("移除")
        remove_btn.clicked.connect(self._remove_card)
        card_toolbar.addWidget(add_btn)
        card_toolbar.addWidget(edit_btn)
        card_toolbar.addWidget(remove_btn)
        card_toolbar.addStretch()
        cards_layout.addLayout(card_toolbar)

        form.add_section_widget(cards_group)

    def _update_ui_from_config(self) -> None:
        super()._update_ui_from_config()
        settings = self._settings()
        raw_cards = settings.get("cards", [])
        self._cards = [dict(entry) for entry in raw_cards if isinstance(entry, dict)]
        self._refresh_cards_list()

    def _add_card(self) -> None:
        card = self._prompt_card()
        if not card:
            return
        self._cards.append(card)
        self._persist_cards()

    def _edit_card(self) -> None:
        index = self._current_card_index()
        if index < 0:
            return
        card = self._prompt_card(self._cards[index])
        if not card:
            return
        self._cards[index] = card
        self._persist_cards()

    def _remove_card(self) -> None:
        index = self._current_card_index()
        if index < 0:
            return
        del self._cards[index]
        self._persist_cards()

    def _on_cards_context_menu(self, pos) -> None:
        item = self.cards_list.itemAt(pos)
        if item is None:
            return
        builder = ContextMenuBuilder(self.cards_list)
        builder.add_action("删除当前行", self._remove_card)
        builder.exec_for(self.cards_list, pos)

    def _persist_cards(self) -> None:
        self._settings()["cards"] = list(self._cards)
        self._refresh_cards_list()
        self._emit_changed()

    def _refresh_cards_list(self) -> None:
        self.cards_list.clear()
        for card in self._cards:
            label = card.get("label", "")
            value = card.get("value", "")
            text = f"{label} ({value})" if value else label
            self.cards_list.addItem(text)

    def _current_card_index(self) -> int:
        return self.cards_list.currentRow()

    def _prompt_card(self, card: Optional[dict] = None) -> Optional[dict]:
        dialog = BaseDialog(
            title="编辑卡牌" if card else "添加卡牌",
            width=360,
            height=180,
            parent=self,
        )

        form_layout = QtWidgets.QFormLayout()
        name_edit = QtWidgets.QLineEdit(card.get("label", "") if card else "")
        value_edit = QtWidgets.QLineEdit(card.get("value", "") if card else "")
        form_layout.addRow("显示名称:", name_edit)
        form_layout.addRow("绑定值:", value_edit)
        dialog.add_layout(form_layout)

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        label = name_edit.text().strip()
        value = value_edit.text().strip()
        if not label:
            return None
        return {"label": label, "value": value}

