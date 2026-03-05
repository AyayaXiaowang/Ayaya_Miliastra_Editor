from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from PyQt6 import QtCore, QtWidgets

from app.ui.dialogs.struct_definition_types import (
    is_dict_type,
    is_list_type,
    is_struct_type,
    normalize_canonical_type_name,
)
from app.ui.dialogs.struct_definition_value_editors import (
    ClickToEditLineEdit,
    DictValueEditor,
    ListValueEditor,
    ScrollSafeComboBox,
)
from app.ui.dialogs.table_edit_helpers import (
    wrap_click_to_edit_line_edit_for_table_cell,
)
from app.ui.foundation.theme_manager import Sizes, ThemeManager
from engine.type_registry import parse_typed_dict_alias


class TwoRowFieldValueCellFactory:
    """负责 TwoRowFieldTableWidget 的“值列”编辑控件创建与取值。

    将“值编辑器的类型分发/控件装配/只读结构体查看按钮/metadata 模式 raw 值”等细节
    从主 Widget 中抽离，避免文件继续膨胀。
    """

    def __init__(
        self,
        *,
        table: QtWidgets.QTableWidget,
        get_supported_types: Callable[[], List[str]],
        get_struct_id_options: Callable[[], List[str]],
        get_dict_type_resolver: Callable[[], Optional[Callable[[str, Mapping[str, Any]], Tuple[str, str]]]],
        get_value_mode: Callable[[], str],
        on_content_changed: Callable[[], None],
        on_struct_view_requested: Callable[[str], None],
        attach_context_menu_forwarding: Callable[[QtWidgets.QWidget], None],
    ) -> None:
        self._table = table
        self._get_supported_types = get_supported_types
        self._get_struct_id_options = get_struct_id_options
        self._get_dict_type_resolver = get_dict_type_resolver
        self._get_value_mode = get_value_mode
        self._on_content_changed = on_content_changed
        self._on_struct_view_requested = on_struct_view_requested
        self._attach_context_menu_forwarding = attach_context_menu_forwarding

    def create_value_cell_widget(
        self,
        type_name: str,
        value: Any,
        *,
        readonly: bool,
    ) -> QtWidgets.QWidget:
        """创建值编辑控件（基础/列表/字典/结构体）。"""
        canonical_type_name = normalize_canonical_type_name(type_name or "")

        if self._get_value_mode() == "metadata":
            return self._create_metadata_cell(value=value, readonly=readonly)

        if not canonical_type_name:
            editor = ClickToEditLineEdit("", self._table)
            editor.setPlaceholderText("无初始值")
            editor.setClearButtonEnabled(True)
            editor.setMinimumHeight(Sizes.INPUT_HEIGHT)
            editor.setReadOnly(readonly)
            if readonly:
                editor.setStyleSheet(ThemeManager.readonly_input_style())
            editor.editingFinished.connect(self._on_content_changed)
            return self._wrap_line_edit_in_value_cell(editor)

        if is_list_type(canonical_type_name):
            list_values: List[str] = []
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                for element in value:
                    list_values.append(str(element))
            editor = ListValueEditor(
                canonical_type_name,
                list_values,
                parent=self._table,
            )
            editor.value_changed.connect(self._on_content_changed)
            if readonly:
                editor.set_read_only(True)
            return editor

        if is_dict_type(canonical_type_name):
            return self._create_dict_editor(
                type_name=type_name,
                value=value,
                readonly=readonly,
            )

        if is_struct_type(canonical_type_name):
            return self._create_struct_editor(
                value=value,
                readonly=readonly,
            )

        value_text = str(value) if value is not None else ""
        editor = ClickToEditLineEdit(value_text, self._table)
        editor.setPlaceholderText("无初始值")
        editor.setClearButtonEnabled(True)
        editor.setMinimumHeight(Sizes.INPUT_HEIGHT)
        editor.setReadOnly(readonly)
        if readonly:
            editor.setStyleSheet(ThemeManager.readonly_input_style())
        editor.editingFinished.connect(self._on_content_changed)
        return self._wrap_line_edit_in_value_cell(editor)

    def extract_value_from_widget(
        self,
        type_name: str,
        value_widget: Optional[QtWidgets.QWidget],
    ) -> Any:
        """从值编辑控件中提取数据。"""
        normalized_type_name = normalize_canonical_type_name(type_name)

        if self._get_value_mode() == "metadata":
            return self._extract_metadata_value(value_widget)

        if is_list_type(normalized_type_name):
            if isinstance(value_widget, ListValueEditor):
                return value_widget.get_values()
            return []

        if is_dict_type(normalized_type_name):
            if isinstance(value_widget, DictValueEditor):
                state = value_widget.get_dict_state()
                raw_entries: List[Tuple[str, str]] = state.get("entries", [])
                mapping: Dict[str, str] = {}
                for key_text, value_text in raw_entries:
                    key_normalized = key_text.strip()
                    if not key_normalized and not value_text:
                        continue
                    mapping[key_normalized] = value_text
                return mapping
            return {}

        if is_struct_type(normalized_type_name):
            if isinstance(value_widget, QtWidgets.QComboBox):
                current_data = value_widget.currentData()
                if isinstance(current_data, str):
                    return current_data
                return value_widget.currentText()

            if isinstance(value_widget, QtWidgets.QWidget):
                combo = value_widget.findChild(QtWidgets.QComboBox)
                if isinstance(combo, QtWidgets.QComboBox):
                    current_data = combo.currentData()
                    if isinstance(current_data, str):
                        return current_data
                    return combo.currentText()

            value_text = ""
            if isinstance(value_widget, QtWidgets.QLineEdit):
                value_text = value_widget.text()
            elif isinstance(value_widget, QtWidgets.QWidget):
                inner_editor = value_widget.findChild(QtWidgets.QLineEdit)
                if isinstance(inner_editor, QtWidgets.QLineEdit):
                    value_text = inner_editor.text()
            return value_text

        value_text = ""
        if isinstance(value_widget, QtWidgets.QLineEdit):
            value_text = value_widget.text()
        elif isinstance(value_widget, QtWidgets.QWidget):
            inner_editor = value_widget.findChild(QtWidgets.QLineEdit)
            if isinstance(inner_editor, QtWidgets.QLineEdit):
                value_text = inner_editor.text()
        return value_text

    def _create_metadata_cell(self, *, value: Any, readonly: bool) -> QtWidgets.QWidget:
        raw_value: Any = value
        display_value: Any = value

        from collections.abc import Mapping as MappingABC  # 避免与 typing.Mapping 混淆

        if isinstance(value, MappingABC):
            if "raw" in value:
                raw_value = value.get("raw")
            if "display" in value:
                display_value = value.get("display")

        text = ""
        if isinstance(display_value, (int, float)):
            int_value = int(display_value)
            text = (
                str(int_value)
                if float(display_value) == float(int_value)
                else str(display_value)
            )
        elif isinstance(display_value, str):
            text = display_value

        editor = ClickToEditLineEdit(text, self._table)
        editor.setPlaceholderText("")
        editor.setClearButtonEnabled(False)
        editor.setMinimumHeight(Sizes.INPUT_HEIGHT)
        editor.setReadOnly(True or readonly)
        editor.setStyleSheet(ThemeManager.readonly_input_style())
        editor.setProperty("two_row_raw_value", raw_value)
        return self._wrap_line_edit_in_value_cell(editor)

    def _extract_metadata_value(self, value_widget: Optional[QtWidgets.QWidget]) -> Any:
        if value_widget is None:
            return ""

        raw_value = value_widget.property("two_row_raw_value")
        if raw_value is not None:
            return raw_value

        line_edit: Optional[QtWidgets.QLineEdit]
        if isinstance(value_widget, QtWidgets.QLineEdit):
            line_edit = value_widget
        else:
            line_edit = value_widget.findChild(QtWidgets.QLineEdit)

        if line_edit is not None:
            raw_value_from_editor = line_edit.property("two_row_raw_value")
            if raw_value_from_editor is not None:
                return raw_value_from_editor
            return line_edit.text()

        return ""

    def _create_dict_editor(
        self,
        *,
        type_name: str,
        value: Any,
        readonly: bool,
    ) -> DictValueEditor:
        key_type_name = "字符串"
        value_type_name = "字符串"
        entries: List[Tuple[str, str]] = []

        # 1) 优先识别别名字典类型（键类型-值类型字典 / 键类型_值类型字典）
        is_typed_dict, alias_key_type, alias_value_type = parse_typed_dict_alias(type_name)
        if is_typed_dict:
            if alias_key_type:
                key_type_name = alias_key_type
            if alias_value_type:
                value_type_name = alias_value_type
        # 2) 其次允许调用方提供 resolver（例如节点图变量的 dict_key_type/dict_value_type 元数据）
        elif isinstance(value, Mapping):
            dict_type_resolver = self._get_dict_type_resolver()
            if dict_type_resolver is not None:
                resolved = dict_type_resolver(type_name, value)
                if (
                    isinstance(resolved, tuple)
                    and len(resolved) == 2
                    and isinstance(resolved[0], str)
                    and isinstance(resolved[1], str)
                ):
                    resolved_key_type = resolved[0].strip()
                    resolved_value_type = resolved[1].strip()
                    if resolved_key_type:
                        key_type_name = resolved_key_type
                    if resolved_value_type:
                        value_type_name = resolved_value_type

        if isinstance(value, Mapping):
            for key, val in value.items():
                entries.append((str(key), str(val)))

        base_type_options = self._get_base_types()
        normalized_options: List[str] = list(base_type_options)
        if key_type_name not in normalized_options:
            normalized_options.insert(0, key_type_name)
        if value_type_name not in normalized_options:
            normalized_options.append(value_type_name)

        editor = DictValueEditor(
            key_type_name,
            value_type_name,
            entries,
            base_type_options=normalized_options,
            parent=self._table,
        )
        editor.value_changed.connect(self._on_content_changed)
        if readonly:
            editor.set_read_only(True)
        return editor

    def _create_struct_editor(
        self,
        *,
        value: Any,
        readonly: bool,
    ) -> QtWidgets.QWidget:
        struct_id_text = ""
        if isinstance(value, str):
            struct_id_text = value.strip()

        struct_id_options = self._get_struct_id_options()
        if not struct_id_options:
            editor = ClickToEditLineEdit(struct_id_text, self._table)
            editor.setPlaceholderText("结构体ID（可选）")
            editor.setMinimumHeight(Sizes.INPUT_HEIGHT)
            editor.setReadOnly(readonly)
            if readonly:
                editor.setStyleSheet(ThemeManager.readonly_input_style())
            editor.editingFinished.connect(self._on_content_changed)
            if readonly and struct_id_text:
                return self._create_readonly_struct_cell_with_view_button(
                    line_edit=editor,
                    struct_id=struct_id_text,
                )
            return self._wrap_line_edit_in_value_cell(editor)

        combo = ScrollSafeComboBox(self._table)
        combo.setMinimumHeight(Sizes.INPUT_HEIGHT)
        combo.setEditable(False)
        combo.addItem("（未选择）", "")

        seen_ids: set[str] = set()
        for struct_id in struct_id_options:
            text = str(struct_id).strip()
            if not text or text in seen_ids:
                continue
            seen_ids.add(text)
            combo.addItem(text, text)

        if struct_id_text:
            index = combo.findData(struct_id_text)
            if index < 0:
                combo.addItem(struct_id_text, struct_id_text)
                index = combo.findData(struct_id_text)
            if index >= 0:
                combo.setCurrentIndex(index)
        else:
            combo.setCurrentIndex(0)

        combo.setEnabled(not readonly)
        if readonly:
            combo.setStyleSheet(ThemeManager.readonly_input_style())
        combo.currentIndexChanged.connect(lambda _index: self._on_content_changed())

        container = QtWidgets.QWidget(self._table)
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_SMALL)
        layout.addWidget(combo, 1)

        if readonly and struct_id_text:
            view_button = QtWidgets.QPushButton("查看", self._table)
            view_button.setFixedHeight(Sizes.INPUT_HEIGHT)
            view_button.setFixedWidth(50)
            view_button.setToolTip(f"查看结构体 {struct_id_text} 的定义")
            view_button.clicked.connect(
                lambda _checked, sid=struct_id_text: self._on_struct_view_requested(sid)
            )
            layout.addWidget(view_button)
            self._attach_context_menu_forwarding(view_button)

        self._attach_context_menu_forwarding(combo)
        self._attach_context_menu_forwarding(container)
        return container

    def _wrap_line_edit_in_value_cell(self, line_edit: QtWidgets.QLineEdit) -> QtWidgets.QWidget:
        container = wrap_click_to_edit_line_edit_for_table_cell(
            self._table,
            line_edit,
        )
        self._attach_context_menu_forwarding(line_edit)
        self._attach_context_menu_forwarding(container)
        return container

    def _create_readonly_struct_cell_with_view_button(
        self,
        *,
        line_edit: QtWidgets.QLineEdit,
        struct_id: str,
    ) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget(self._table)
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_SMALL)

        text_container = wrap_click_to_edit_line_edit_for_table_cell(
            self._table,
            line_edit,
        )
        layout.addWidget(text_container, 1)

        view_button = QtWidgets.QPushButton("查看", self._table)
        view_button.setFixedHeight(Sizes.INPUT_HEIGHT)
        view_button.setFixedWidth(50)
        view_button.setToolTip(f"查看结构体 {struct_id} 的定义")
        view_button.clicked.connect(
            lambda _checked, sid=struct_id: self._on_struct_view_requested(sid)
        )
        layout.addWidget(view_button)

        self._attach_context_menu_forwarding(line_edit)
        self._attach_context_menu_forwarding(text_container)
        self._attach_context_menu_forwarding(view_button)
        self._attach_context_menu_forwarding(container)
        return container

    def _get_base_types(self) -> List[str]:
        base_types: List[str] = []
        for type_name in self._get_supported_types():
            normalized = normalize_canonical_type_name(type_name)
            if (
                not is_list_type(normalized)
                and not is_dict_type(normalized)
                and not is_struct_type(normalized)
            ):
                base_types.append(normalized)
        if not base_types:
            base_types.append("字符串")
        seen: set[str] = set()
        result: List[str] = []
        for name in base_types:
            if name in seen:
                continue
            seen.add(name)
            result.append(name)
        return result


__all__ = ["TwoRowFieldValueCellFactory"]


