from __future__ import annotations

from typing import Any

from PyQt6 import QtCore, QtWidgets

from app.ui.panels.ui.ui_control_group_collapsible_section import CollapsibleSection
from .base import BaseWidgetConfigPanel, WidgetConfigForm
from .card_selector_editor_dialog import CardPoolEditorDialog


class CardSelectorConfigPanel(BaseWidgetConfigPanel):
    """卡牌选择器配置面板"""

    def _setup_ui(self) -> None:
        self._cards: list[dict[str, Any]] = []
        layout = QtWidgets.QVBoxLayout(self)

        form = WidgetConfigForm(self)
        layout.addWidget(form)

        # 兼容旧字段：仍保留“选择模式”
        self.selection_mode_combo = form.add_combo_box(
            "选择模式:",
            "selection_mode",
            ["单选", "多选"],
            default_text="单选",
        )

        # 折叠分组：已知卡牌设置
        known_section = CollapsibleSection("已知卡牌设置")
        known_section.setCollapsed(False)
        known_widget = QtWidgets.QWidget()
        known_layout = QtWidgets.QVBoxLayout(known_widget)
        known_layout.setContentsMargins(0, 0, 0, 0)

        self.known_show_icon_check = QtWidgets.QCheckBox("显示卡牌图标")
        self._bind_checkbox("known_show_icon", self.known_show_icon_check, default=True)
        known_layout.addWidget(self.known_show_icon_check)

        self.known_show_title_check = QtWidgets.QCheckBox("显示卡牌标题")
        self._bind_checkbox("known_show_title", self.known_show_title_check, default=True)
        known_layout.addWidget(self.known_show_title_check)

        self.known_show_desc_check = QtWidgets.QCheckBox("显示卡牌描述")
        self._bind_checkbox("known_show_description", self.known_show_desc_check, default=True)
        known_layout.addWidget(self.known_show_desc_check)

        known_layout.addStretch()
        known_section.add_widget(known_widget)
        layout.addWidget(known_section)

        # 折叠分组：未知卡牌设置
        unknown_section = CollapsibleSection("未知卡牌设置")
        unknown_section.setCollapsed(False)
        unknown_widget = QtWidgets.QWidget()
        unknown_layout = QtWidgets.QVBoxLayout(unknown_widget)
        unknown_layout.setContentsMargins(0, 0, 0, 0)

        self.unknown_show_result_check = QtWidgets.QCheckBox("选择后展示结果")
        self.unknown_show_result_check.stateChanged.connect(self._apply_unknown_state)
        self._bind_checkbox("unknown_show_result", self.unknown_show_result_check, default=True)
        unknown_layout.addWidget(self.unknown_show_result_check)

        close_row = QtWidgets.QWidget()
        close_row_layout = QtWidgets.QHBoxLayout(close_row)
        close_row_layout.setContentsMargins(0, 0, 0, 0)
        close_row_layout.setSpacing(6)
        close_row_layout.addWidget(QtWidgets.QLabel("结果页关闭方式:"))
        self.result_close_method_combo = QtWidgets.QComboBox()
        self.result_close_method_combo.addItems(["倒计时关闭", "手动关闭"])
        self.result_close_method_combo.currentTextChanged.connect(self._apply_close_method_state)
        self._bind_combo_box("result_close_method", self.result_close_method_combo, default_text="手动关闭")
        close_row_layout.addWidget(self.result_close_method_combo, 1)
        unknown_layout.addWidget(close_row)

        self.countdown_row = QtWidgets.QWidget()
        countdown_layout = QtWidgets.QHBoxLayout(self.countdown_row)
        countdown_layout.setContentsMargins(0, 0, 0, 0)
        countdown_layout.setSpacing(6)
        countdown_layout.addWidget(QtWidgets.QLabel("倒计时时长(s):"))
        self.countdown_spin = QtWidgets.QDoubleSpinBox()
        self.countdown_spin.setRange(0.0, 99999.0)
        self.countdown_spin.setSingleStep(0.5)
        self._bind_spin_box("result_countdown_seconds", self.countdown_spin, default=3.0)
        countdown_layout.addWidget(self.countdown_spin, 1)
        unknown_layout.addWidget(self.countdown_row)

        unknown_layout.addStretch()
        unknown_section.add_widget(unknown_widget)
        layout.addWidget(unknown_section)

        # 折叠分组：卡牌库设置
        pool_section = CollapsibleSection("卡牌库设置")
        pool_section.setCollapsed(False)
        pool_widget = QtWidgets.QWidget()
        pool_layout = QtWidgets.QVBoxLayout(pool_widget)
        pool_layout.setContentsMargins(0, 0, 0, 0)

        self.cards_preview = QtWidgets.QListWidget()
        self.cards_preview.setMaximumHeight(180)
        self.cards_preview.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        pool_layout.addWidget(self.cards_preview)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        self.edit_btn = QtWidgets.QPushButton("详情编辑...")
        self.edit_btn.clicked.connect(self._open_card_pool_editor)
        btn_row.addWidget(self.edit_btn)
        pool_layout.addLayout(btn_row)

        pool_section.add_widget(pool_widget)
        layout.addWidget(pool_section)

    def _update_ui_from_config(self) -> None:
        super()._update_ui_from_config()
        settings = self._settings()
        raw_cards = settings.get("cards", [])
        self._cards = self._normalize_cards([entry for entry in raw_cards if isinstance(entry, dict)])
        self._refresh_cards_preview()
        self._apply_unknown_state()
        self._apply_close_method_state()

    # ----------------------------------------------------------------------------------
    # Cards
    # ----------------------------------------------------------------------------------
    def _normalize_cards(self, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        used_ids: set[int] = set()
        next_id = 1
        normalized: list[dict[str, Any]] = []
        for entry in cards:
            card = dict(entry)
            raw_id = card.get("card_id", card.get("id", 0))
            card_id = raw_id if isinstance(raw_id, int) else 0
            if card_id <= 0 or card_id in used_ids:
                while next_id in used_ids:
                    next_id += 1
                card_id = next_id
            used_ids.add(card_id)
            next_id = max(next_id, card_id + 1)
            card["card_id"] = card_id
            normalized.append(card)
        return normalized

    def _refresh_cards_preview(self) -> None:
        self.cards_preview.clear()
        for card in self._cards:
            card_id = card.get("card_id", 0)
            card_type = str(card.get("card_type") or card.get("type") or "").strip()
            label = str(card.get("card_title") or card.get("label") or "").strip()
            if card_type:
                text = f"? 序号 {card_id} | {card_type} | {label}"
            else:
                text = f"? 序号 {card_id} | {label}" if label else f"? 序号 {card_id}"
            self.cards_preview.addItem(text)

    def _persist_cards(self) -> None:
        self._settings()["cards"] = list(self._cards)
        self._refresh_cards_preview()
        self._emit_changed()

    # ----------------------------------------------------------------------------------
    # UI states
    # ----------------------------------------------------------------------------------
    def _apply_unknown_state(self) -> None:
        enabled = self.unknown_show_result_check.isChecked()
        self.result_close_method_combo.setEnabled(enabled)
        self.countdown_spin.setEnabled(enabled)
        self.countdown_row.setEnabled(enabled)

    def _apply_close_method_state(self) -> None:
        method = self.result_close_method_combo.currentText().strip()
        show_countdown = method == "倒计时关闭"
        self.countdown_row.setVisible(show_countdown)

    # ----------------------------------------------------------------------------------
    # Editor dialog
    # ----------------------------------------------------------------------------------
    def _open_card_pool_editor(self) -> None:
        dialog = CardPoolEditorDialog(self._cards, parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        updated_cards = dialog.get_cards()
        old_by_id: dict[int, dict[str, Any]] = {}
        for old in self._cards:
            raw_id = old.get("card_id", 0)
            if isinstance(raw_id, int) and raw_id > 0:
                old_by_id[raw_id] = dict(old)

        merged: list[dict[str, Any]] = []
        for entry in updated_cards:
            raw_id = entry.get("card_id", 0)
            card_id = raw_id if isinstance(raw_id, int) else 0
            base = dict(old_by_id.get(card_id, {}))
            base.update(entry)
            merged.append(base)

        self._cards = self._normalize_cards(merged)
        self._persist_cards()

