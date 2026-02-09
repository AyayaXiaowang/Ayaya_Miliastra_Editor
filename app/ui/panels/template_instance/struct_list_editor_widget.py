"""结构体列表变量的单元格编辑组件。

从 variables_tab.py 中拆出，避免变量标签页文件职责过载。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.theme_manager import Sizes, ThemeManager
from app.ui.foundation.toolbar_utils import apply_standard_toolbar
from app.ui.dialogs.struct_list_item_dialog import (
    StructListItemEditDialog,
    StructListItemViewerDialog,
)


class StructListEditorWidget(QtWidgets.QWidget):
    """
    自定义变量用的“结构体列表”值编辑组件。

    约定的数据结构：
    {
        "struct_id": str,                 # 选中的基础结构体 ID
        "items": [
            {
                "name": str,             # 可选的人类可读名称
                "fields": {              # 按字段名存放当前条目的数据值（保留原始值类型）
                    "<字段名>": "<值>",
                    ...
                },
            },
            ...
        ],
    }
    """

    value_changed = QtCore.pyqtSignal()

    def __init__(
        self,
        *,
        struct_id_options: Sequence[str],
        resource_manager: Optional[object],
        value: Any,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._resource_manager = resource_manager
        self._is_read_only: bool = False
        self._struct_id_options: list[str] = [
            str(text).strip() for text in struct_id_options if str(text).strip()
        ]
        self._struct_id: str = ""
        self._items: list[dict[str, Any]] = []

        self._setup_ui()
        self._apply_struct_id_options()
        self._load_value(value)

    def set_read_only(self, read_only: bool) -> None:
        """设置为只读查看模式。

        只读模式下：
        - 禁用结构体下拉与新增/删除；
        - 仍允许选择条目并点击“查看”打开只读详情，以便在外部变量等只读视图中浏览数据。
        """
        target = bool(read_only)
        if self._is_read_only == target:
            return
        self._is_read_only = target
        self.struct_combo.setEnabled(not self._is_read_only)
        self._update_buttons()

    # ------------------------------------------------------------------ UI 组装

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(
            Sizes.SPACING_SMALL,
            Sizes.SPACING_SMALL,
            Sizes.SPACING_SMALL,
            Sizes.SPACING_SMALL,
        )
        layout.setSpacing(Sizes.SPACING_SMALL)

        toolbar = QtWidgets.QHBoxLayout()
        apply_standard_toolbar(toolbar)

        struct_label = QtWidgets.QLabel("结构体:", self)
        self.struct_combo = QtWidgets.QComboBox(self)
        self.struct_combo.setMinimumWidth(200)
        self.struct_combo.setMinimumHeight(Sizes.INPUT_HEIGHT)

        toolbar.addWidget(struct_label)
        toolbar.addWidget(self.struct_combo)
        toolbar.addStretch(1)

        self.add_button = QtWidgets.QPushButton("+ 添加条目", self)
        self.remove_button = QtWidgets.QPushButton("删除", self)
        self.edit_button = QtWidgets.QPushButton("编辑", self)

        for button in (self.add_button, self.remove_button, self.edit_button):
            button.setMinimumHeight(Sizes.BUTTON_HEIGHT)
            button.setStyleSheet(ThemeManager.button_style())

        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.remove_button)
        toolbar.addWidget(self.edit_button)

        layout.addLayout(toolbar)

        self.list_widget = QtWidgets.QListWidget(self)
        self.list_widget.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.list_widget.setStyleSheet(ThemeManager.list_style())
        layout.addWidget(self.list_widget, 1)

        self.hint_label = QtWidgets.QLabel(
            "请选择上方的结构体后再添加列表条目（每一条都使用同一结构体的数据结构）。", self
        )
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(ThemeManager.subtle_info_style())
        layout.addWidget(self.hint_label)

        self.struct_combo.currentIndexChanged.connect(self._on_struct_changed)
        self.add_button.clicked.connect(self._on_add_item)
        self.remove_button.clicked.connect(self._on_remove_item)
        self.edit_button.clicked.connect(self._on_edit_item)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.currentRowChanged.connect(lambda _row: self._update_buttons())

        self._update_buttons()

    def _apply_struct_id_options(self) -> None:
        self.struct_combo.blockSignals(True)
        self.struct_combo.clear()
        self.struct_combo.addItem("（请选择结构体）", "")
        for struct_id in self._struct_id_options:
            self.struct_combo.addItem(struct_id, struct_id)
        self.struct_combo.blockSignals(False)

    # ------------------------------------------------------------------ 数据加载与导出

    def _load_value(self, value: Any) -> None:
        self._struct_id = ""
        self._items = []

        if isinstance(value, Mapping):
            raw_struct_id = value.get("struct_id")
            if isinstance(raw_struct_id, str):
                self._struct_id = raw_struct_id.strip()
            raw_items = value.get("items")
            if isinstance(raw_items, list):
                for entry in raw_items:
                    if not isinstance(entry, Mapping):
                        continue
                    name_value = entry.get("name", "")
                    name_text = str(name_value).strip() if isinstance(name_value, str) else ""
                    fields_value = entry.get("fields", {})
                    fields_dict: dict[str, Any] = {}
                    if isinstance(fields_value, Mapping):
                        for key, field_val in fields_value.items():
                            key_text = str(key).strip()
                            if not key_text:
                                continue
                            fields_dict[key_text] = field_val
                    self._items.append(
                        {
                            "name": name_text,
                            "fields": fields_dict,
                        }
                    )

        if self._struct_id:
            index = self.struct_combo.findData(self._struct_id)
            if index < 0:
                # 当前结构体 ID 不在候选列表中：追加一项以避免用户丢失配置
                self.struct_combo.addItem(self._struct_id, self._struct_id)
                index = self.struct_combo.findData(self._struct_id)
            if index >= 0:
                self.struct_combo.setCurrentIndex(index)

        self._rebuild_list()
        self._update_buttons()

    def get_value(self) -> dict[str, Any]:
        """导出当前结构体列表值。"""
        items: list[dict[str, Any]] = []
        for index, entry in enumerate(self._items):
            name_value = entry.get("name", "")
            name_text = str(name_value).strip() if isinstance(name_value, str) else ""
            fields_value = entry.get("fields", {})
            fields_dict: dict[str, Any] = {}
            if isinstance(fields_value, Mapping):
                for key, field_val in fields_value.items():
                    key_text = str(key).strip()
                    if not key_text:
                        continue
                    fields_dict[key_text] = field_val
            items.append(
                {
                    "name": name_text or f"条目{index + 1}",
                    "fields": fields_dict,
                }
            )

        return {
            "struct_id": self._struct_id,
            "items": items,
        }

    # ------------------------------------------------------------------ 列表与按钮状态

    def _rebuild_list(self) -> None:
        self.list_widget.clear()
        for index, entry in enumerate(self._items):
            display_text = self._build_item_display_text(index, entry)
            item = QtWidgets.QListWidgetItem(display_text, self.list_widget)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, index)

    def _build_item_display_text(self, index: int, entry: Mapping[str, Any]) -> str:
        name_value = entry.get("name", "")
        name_text = str(name_value).strip() if isinstance(name_value, str) else ""
        fields_value = entry.get("fields", {})
        summary = ""
        if isinstance(fields_value, Mapping) and fields_value:
            for key, field_val in fields_value.items():
                key_text = str(key).strip()
                if not key_text:
                    continue
                summary = f"{key_text}={field_val}"
                break
        if not name_text and not summary:
            return f"{index + 1}"
        if name_text and not summary:
            return f"{index + 1}  {name_text}"
        if not name_text and summary:
            return f"{index + 1}  {summary}"
        return f"{index + 1}  {name_text}  ({summary})"

    def _update_buttons(self) -> None:
        has_struct = bool(self._struct_id)
        has_selection = self.list_widget.currentRow() >= 0
        has_items = bool(self._items)

        if self._is_read_only:
            self.edit_button.setText("查看")
        else:
            self.edit_button.setText("编辑")

        self.add_button.setEnabled(has_struct and (not self._is_read_only))
        self.remove_button.setEnabled(
            has_struct and has_selection and has_items and (not self._is_read_only)
        )
        # 只读模式下仍允许查看条目详情
        self.edit_button.setEnabled(has_struct and has_selection and has_items)

        if has_struct:
            self.hint_label.setText(
                "已选择结构体，使用下方列表维护结构体列表中的各个条目，双击或点击“编辑”可配置字段值。"
            )
        else:
            self.hint_label.setText(
                "请选择上方的结构体后再添加列表条目（每一条都使用同一结构体的数据结构）。"
            )

    # ------------------------------------------------------------------ 事件处理

    def _on_struct_changed(self, index: int) -> None:
        if self._is_read_only:
            return
        data = self.struct_combo.itemData(index)
        if isinstance(data, str):
            self._struct_id = data.strip()
        else:
            self._struct_id = ""
        self._update_buttons()
        self.value_changed.emit()

    def _on_add_item(self) -> None:
        if self._is_read_only:
            return
        if not self._struct_id:
            return
        new_entry = {
            "name": "",
            "fields": {},
        }
        self._items.append(new_entry)
        self._rebuild_list()
        last_row = self.list_widget.count() - 1
        if last_row >= 0:
            self.list_widget.setCurrentRow(last_row)
        self._update_buttons()
        self.value_changed.emit()

    def _on_remove_item(self) -> None:
        if self._is_read_only:
            return
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._items):
            return
        del self._items[row]
        self._rebuild_list()
        if self._items and row >= 0:
            self.list_widget.setCurrentRow(min(row, len(self._items) - 1))
        self._update_buttons()
        self.value_changed.emit()

    def _on_edit_item(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._items):
            return
        self._edit_item_at_index(row)

    def _on_item_double_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        index_value = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(index_value, int):
            self._edit_item_at_index(index_value)

    def _edit_item_at_index(self, index: int) -> None:
        if not self._struct_id:
            return
        entry = self._items[index]
        fields_value = entry.get("fields", {})
        if isinstance(fields_value, Mapping):
            current_fields: dict[str, Any] = dict(fields_value)
        else:
            current_fields = {}

        name_value = entry.get("name", "")
        entry_name = str(name_value).strip() if isinstance(name_value, str) else ""
        display_name = entry_name or f"条目{index + 1}"

        if self._is_read_only:
            dialog = StructListItemViewerDialog(
                struct_id=self._struct_id,
                item_name=display_name,
                fields=current_fields,
                parent=self,
            )
            dialog.exec()
            return

        if self._resource_manager is None:
            return
        dialog = StructListItemEditDialog(
            struct_id=self._struct_id,
            resource_manager=self._resource_manager,
            initial_values=current_fields,
            parent=self,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        updated_fields = dialog.get_result()
        entry["fields"] = updated_fields
        self._items[index] = entry
        self._rebuild_list()
        self._update_buttons()
        self.value_changed.emit()


__all__ = ["StructListEditorWidget"]


