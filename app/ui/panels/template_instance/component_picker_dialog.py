"""通用组件选择器对话框（带搜索）。

用于 ComponentsTab 的“添加通用组件”入口：
- 支持搜索过滤（不区分大小写；中文按子串匹配）
- 以列表形式展示候选组件名称，并在 tooltip 中附带说明与适用实体信息
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation import dialog_utils
from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager


class ComponentPickerDialog(BaseDialog):
    """添加通用组件：选择组件类型对话框。"""

    def __init__(
        self,
        component_types: List[str],
        component_definitions: Dict[str, Dict[str, object]],
        parent: Optional[QtWidgets.QWidget] = None,
        *,
        title: str = "添加通用组件",
    ) -> None:
        self._component_types = list(component_types)
        self._definitions = dict(component_definitions)
        self._selected_component_type: str = ""

        super().__init__(
            title=title,
            width=560,
            height=640,
            parent=parent,
        )

        self._build_content()

    def _apply_styles(self) -> None:
        self.setStyleSheet(ThemeManager.dialog_surface_style())

    def _build_content(self) -> None:
        layout = self.content_layout

        hint = QtWidgets.QLabel(
            "选择要添加到当前对象上的通用组件。\n"
            "提示：列表仅展示“当前上下文允许添加”的组件类型。",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(ThemeManager.hint_text_style())
        layout.addWidget(hint)

        search_row = QtWidgets.QWidget(self)
        search_layout = QtWidgets.QHBoxLayout(search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(Sizes.SPACING_SMALL)

        search_label = QtWidgets.QLabel("搜索:", search_row)
        search_layout.addWidget(search_label)

        self._search_edit = QtWidgets.QLineEdit(search_row)
        self._search_edit.setStyleSheet(ThemeManager.input_style())
        self._search_edit.setPlaceholderText("输入关键字过滤组件…")
        self._search_edit.textChanged.connect(self._apply_filter)
        search_layout.addWidget(self._search_edit, 1)

        layout.addWidget(search_row)

        self._list_widget = QtWidgets.QListWidget(self)
        self._list_widget.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self._list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list_widget, 1)

        self._populate_items(self._component_types)

        ok_button = self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("添加")
            ok_button.setEnabled(False)
        cancel_button = self.button_box.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        if cancel_button is not None:
            cancel_button.setText("取消")

    def _populate_items(self, component_types: List[str]) -> None:
        self._list_widget.clear()

        sorted_types = list(component_types)
        sorted_types.sort(key=lambda text: str(text).casefold())

        for component_type in sorted_types:
            item = QtWidgets.QListWidgetItem(f"⚙️ {component_type}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, component_type)

            definition = self._definitions.get(component_type, {})
            description = str(definition.get("description") or "").strip()
            applicable_raw = definition.get("applicable_entities")
            applicable_text = ""
            if isinstance(applicable_raw, list):
                applicable_text = "、".join(str(x) for x in applicable_raw if str(x))
            elif applicable_raw is not None:
                applicable_text = str(applicable_raw).strip()

            tooltip_lines: list[str] = [component_type]
            if description:
                tooltip_lines.append(description)
            if applicable_text:
                tooltip_lines.append(f"适用实体: {applicable_text}")
            item.setToolTip("\n".join(tooltip_lines))

            self._list_widget.addItem(item)

    def _apply_filter(self, text: str) -> None:
        query = str(text or "").strip().casefold()
        if not query:
            for index in range(self._list_widget.count()):
                item = self._list_widget.item(index)
                if item is not None:
                    item.setHidden(False)
            return

        for index in range(self._list_widget.count()):
            item = self._list_widget.item(index)
            if item is None:
                continue
            component_type = str(item.data(QtCore.Qt.ItemDataRole.UserRole) or "")
            haystack = (component_type + " " + item.text()).casefold()
            item.setHidden(query not in haystack)

    def _on_selection_changed(self) -> None:
        item = self._list_widget.currentItem()
        component_type = (
            str(item.data(QtCore.Qt.ItemDataRole.UserRole) or "") if item else ""
        )
        self._selected_component_type = component_type

        ok_button = self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(bool(component_type))

    def _on_item_double_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        component_type = str(item.data(QtCore.Qt.ItemDataRole.UserRole) or "")
        if not component_type:
            return
        self._selected_component_type = component_type
        self.accept()

    def validate(self) -> bool:
        if not self._selected_component_type:
            dialog_utils.show_warning_dialog(self, "提示", "请先选择一个通用组件。")
            return False
        return True

    def get_selected_component_type(self) -> str:
        return self._selected_component_type


__all__ = ["ComponentPickerDialog"]


