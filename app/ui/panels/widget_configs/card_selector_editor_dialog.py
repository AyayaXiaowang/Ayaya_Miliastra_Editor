from __future__ import annotations

import json
from typing import Any, Optional

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.toolbar_utils import apply_standard_toolbar

__all__ = ["CardPoolEditorDialog"]


CARD_TYPE_OPTIONS = ["已知卡牌", "未知卡牌"]
TAG_COLOR_OPTIONS = [
    "1 白色",
    "2 绿色",
    "3 蓝色",
    "4 紫色",
    "5 橙色",
    "6 红色",
]


class CardPoolEditorDialog(BaseDialog):
    """卡牌库内容编辑器（表格）。"""

    def __init__(
        self,
        cards: list[dict[str, Any]],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(
            title="卡牌库内容编辑器",
            width=980,
            height=680,
            use_scroll=False,
            parent=parent,
        )
        self._next_card_id: int = 1
        self._setup_table()
        self._load_cards(cards)

    # ----------------------------------------------------------------------------------
    # UI
    # ----------------------------------------------------------------------------------
    def _setup_table(self) -> None:
        toolbar = QtWidgets.QHBoxLayout()
        apply_standard_toolbar(toolbar)
        add_btn = QtWidgets.QPushButton("+ 新增行")
        add_btn.clicked.connect(self._add_row)
        remove_btn = QtWidgets.QPushButton("删除当前行")
        remove_btn.clicked.connect(self._remove_current_row)
        copy_btn = QtWidgets.QPushButton("复制")
        copy_btn.clicked.connect(self._copy_rows)
        paste_btn = QtWidgets.QPushButton("粘贴")
        paste_btn.clicked.connect(self._paste_rows)
        import_btn = QtWidgets.QPushButton("导入...")
        import_btn.clicked.connect(self._import_json)
        export_btn = QtWidgets.QPushButton("导出...")
        export_btn.clicked.connect(self._export_json)

        toolbar.addWidget(copy_btn)
        toolbar.addWidget(paste_btn)
        toolbar.addStretch()
        toolbar.addWidget(import_btn)
        toolbar.addWidget(export_btn)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(remove_btn)

        toolbar_widget = QtWidgets.QWidget()
        toolbar_widget.setLayout(toolbar)
        self.add_widget(toolbar_widget)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            [
                "卡牌序号",
                "卡牌类型",
                "卡牌图标",
                "卡牌标题",
                "卡牌描述",
                "标签颜色",
                "标签描述",
            ]
        )
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.add_widget(self.table)

    # ----------------------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------------------
    def get_cards(self) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for row in range(self.table.rowCount()):
            cards.append(self._read_row(row))
        return cards

    # ----------------------------------------------------------------------------------
    # Rows
    # ----------------------------------------------------------------------------------
    def _load_cards(self, cards: list[dict[str, Any]]) -> None:
        self.table.setRowCount(0)
        max_id = 0
        for entry in cards:
            if not isinstance(entry, dict):
                continue
            card_id = int(entry.get("card_id") or entry.get("id") or entry.get("序号") or 0)
            if card_id > max_id:
                max_id = card_id
            self._append_row(
                card_id=card_id or 0,
                card_type=str(entry.get("card_type") or entry.get("type") or "已知卡牌"),
                card_icon=str(entry.get("card_icon") or entry.get("card_image") or entry.get("icon") or ""),
                card_title=str(entry.get("card_title") or entry.get("title") or ""),
                card_description=str(entry.get("card_description") or entry.get("description") or ""),
                tag_color=str(entry.get("tag_color") or entry.get("color") or TAG_COLOR_OPTIONS[0]),
                tag_description=str(entry.get("tag_description") or entry.get("tag_desc") or ""),
            )
        self._next_card_id = max_id + 1 if max_id > 0 else 1

    def _append_row(
        self,
        *,
        card_id: int,
        card_type: str,
        card_icon: str,
        card_title: str,
        card_description: str,
        tag_color: str,
        tag_description: str,
    ) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        id_item = QtWidgets.QTableWidgetItem(str(card_id))
        id_item.setFlags(id_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 0, id_item)

        type_combo = QtWidgets.QComboBox()
        type_combo.addItems(CARD_TYPE_OPTIONS)
        type_combo.setCurrentText(card_type if card_type in CARD_TYPE_OPTIONS else CARD_TYPE_OPTIONS[0])
        self.table.setCellWidget(row, 1, type_combo)

        icon_row = QtWidgets.QWidget()
        icon_layout = QtWidgets.QHBoxLayout(icon_row)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setSpacing(4)
        icon_edit = QtWidgets.QLineEdit(card_icon)
        icon_edit.setPlaceholderText("图标资源路径")
        icon_btn = QtWidgets.QPushButton("浏览...")
        icon_btn.setFixedWidth(60)
        icon_btn.clicked.connect(lambda _=False, edit=icon_edit: self._choose_image_for(edit))
        icon_layout.addWidget(icon_edit, 1)
        icon_layout.addWidget(icon_btn)
        self.table.setCellWidget(row, 2, icon_row)

        title_edit = QtWidgets.QLineEdit(card_title)
        self.table.setCellWidget(row, 3, title_edit)

        desc_edit = QtWidgets.QLineEdit(card_description)
        self.table.setCellWidget(row, 4, desc_edit)

        color_combo = QtWidgets.QComboBox()
        color_combo.addItems(TAG_COLOR_OPTIONS)
        color_combo.setCurrentText(tag_color if tag_color in TAG_COLOR_OPTIONS else TAG_COLOR_OPTIONS[0])
        self.table.setCellWidget(row, 5, color_combo)

        tag_desc_edit = QtWidgets.QLineEdit(tag_description)
        self.table.setCellWidget(row, 6, tag_desc_edit)

    def _read_row(self, row: int) -> dict[str, Any]:
        id_item = self.table.item(row, 0)
        card_id_text = id_item.text().strip() if id_item is not None else ""
        card_id = int(card_id_text) if card_id_text.isdigit() else row + 1

        type_combo = self.table.cellWidget(row, 1)
        card_type = type_combo.currentText().strip() if isinstance(type_combo, QtWidgets.QComboBox) else "已知卡牌"

        icon_row = self.table.cellWidget(row, 2)
        icon_edit: Optional[QtWidgets.QLineEdit] = None
        if isinstance(icon_row, QtWidgets.QWidget):
            icon_edit = icon_row.findChild(QtWidgets.QLineEdit)
        card_icon = icon_edit.text().strip() if isinstance(icon_edit, QtWidgets.QLineEdit) else ""

        title_edit = self.table.cellWidget(row, 3)
        card_title = title_edit.text().strip() if isinstance(title_edit, QtWidgets.QLineEdit) else ""

        desc_edit = self.table.cellWidget(row, 4)
        card_description = desc_edit.text().strip() if isinstance(desc_edit, QtWidgets.QLineEdit) else ""

        color_combo = self.table.cellWidget(row, 5)
        tag_color = color_combo.currentText().strip() if isinstance(color_combo, QtWidgets.QComboBox) else TAG_COLOR_OPTIONS[0]

        tag_desc_edit = self.table.cellWidget(row, 6)
        tag_description = tag_desc_edit.text().strip() if isinstance(tag_desc_edit, QtWidgets.QLineEdit) else ""

        return {
            "card_id": card_id,
            "card_type": card_type,
            "card_icon": card_icon,
            "card_title": card_title,
            "card_description": card_description,
            "tag_color": tag_color,
            "tag_description": tag_description,
        }

    def _add_row(self) -> None:
        card_id = self._next_card_id
        self._next_card_id += 1
        self._append_row(
            card_id=card_id,
            card_type="已知卡牌",
            card_icon="",
            card_title="",
            card_description="",
            tag_color=TAG_COLOR_OPTIONS[0],
            tag_description="",
        )

    def _remove_current_row(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        self.table.removeRow(row)

    # ----------------------------------------------------------------------------------
    # Clipboard
    # ----------------------------------------------------------------------------------
    def _selected_rows(self) -> list[int]:
        indexes = self.table.selectedIndexes()
        rows = sorted({idx.row() for idx in indexes})
        return rows

    def _copy_rows(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        lines: list[str] = []
        for row in rows:
            data = self._read_row(row)
            cols = [
                str(data.get("card_id", "")),
                str(data.get("card_type", "")),
                str(data.get("card_icon", "")),
                str(data.get("card_title", "")),
                str(data.get("card_description", "")),
                str(data.get("tag_color", "")),
                str(data.get("tag_description", "")),
            ]
            lines.append("\t".join(cols))
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))

    def _paste_rows(self) -> None:
        text = QtWidgets.QApplication.clipboard().text() or ""
        lines = [line for line in (text.splitlines() if text else []) if line.strip()]
        if not lines:
            return
        for line in lines:
            cols = [col.strip() for col in line.split("\t")]
            if len(cols) < 6:
                continue

            # 支持两种格式：
            # - 7列：id, type, icon, title, desc, color, tag_desc
            # - 6列：type, icon, title, desc, color, tag_desc
            if len(cols) >= 7 and cols[0].isdigit():
                _, card_type, card_icon, card_title, card_description, tag_color, tag_description = cols[:7]
            else:
                card_type, card_icon, card_title, card_description, tag_color, tag_description = cols[:6]

            card_id = self._next_card_id
            self._next_card_id += 1
            self._append_row(
                card_id=card_id,
                card_type=card_type or "已知卡牌",
                card_icon=card_icon,
                card_title=card_title,
                card_description=card_description,
                tag_color=tag_color or TAG_COLOR_OPTIONS[0],
                tag_description=tag_description,
            )

    # ----------------------------------------------------------------------------------
    # Import / Export
    # ----------------------------------------------------------------------------------
    def _export_json(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出卡牌库",
            "",
            "JSON (*.json);;All Files (*.*)",
        )
        if not file_path:
            return
        payload = self.get_cards()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _import_json(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "导入卡牌库",
            "",
            "JSON (*.json);;All Files (*.*)",
        )
        if not file_path:
            return
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("导入失败：配置文件格式不正确，需要列表格式")
        self._load_cards([entry for entry in data if isinstance(entry, dict)])

    # ----------------------------------------------------------------------------------
    # Utilities
    # ----------------------------------------------------------------------------------
    def _choose_image_for(self, edit: QtWidgets.QLineEdit) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择图标资源",
            "",
            "Images (*.png *.jpg *.jpeg *.svg);;All Files (*.*)",
        )
        if file_path:
            edit.setText(file_path)


