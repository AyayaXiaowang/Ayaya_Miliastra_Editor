from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence, List

from PyQt6 import QtWidgets

from engine.configs.resource_types import ResourceType
from engine.configs.specialized.struct_definitions_data import (
    get_struct_payload,
    list_struct_ids,
)
from engine.graph.models.entity_templates import get_all_variable_types
from ui.dialogs.struct_definition_types import param_type_to_canonical
from ui.foundation import dialog_utils
from ui.foundation.base_widgets import BaseDialog
from ui.foundation.theme_manager import ThemeManager, Sizes
from ui.widgets.two_row_field_table_widget import TwoRowFieldTableWidget


class StructListItemEditDialog(BaseDialog):
    """结构体列表条目编辑对话框。

    用途：
    - 在已选定结构体 ID 的前提下，为当前自定义变量中的某个“结构体列表”条目配置字段值；
    - 使用通用的 `TwoRowFieldTableWidget` 组件按“字段名 / 数据类型 / 数据值”展示结构体字段，
      字段名与数据类型均来源于结构体定义，仅允许编辑“数据值”；
    - 支持基础类型、列表、字典以及结构体/结构体列表字段：
      * 列表/字典字段以内联子表格形式编辑元素/键值对；
      * 结构体/结构体列表字段通过下拉框选择结构体 ID（若提供结构体列表）或手动输入 ID。

    输入：
    - struct_id: 结构体定义资源 ID；
    - resource_manager: 用于加载 STRUCT_DEFINITION 资源并提供结构体 ID 列表；
    - initial_values: 按字段名存放的当前条目值字典，值可以是字符串、列表或字典，类型由结构体字段定义决定。

    输出：
    - get_result() -> Dict[str, Any]：按字段名返回最新的值字典，列表/字典字段以 Python 列表/字典形式返回。
    """

    def __init__(
        self,
        *,
        struct_id: str,
        resource_manager: Any,
        initial_values: Optional[Mapping[str, Any]] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        self._struct_id: str = struct_id
        self._resource_manager: Any = resource_manager
        self._initial_values: Dict[str, Any] = (
            dict(initial_values) if isinstance(initial_values, Mapping) else {}
        )
        self._result: Dict[str, Any] = {}

        super().__init__(
            title="编辑结构体条目",
            width=720,
            height=520,
            parent=parent,
        )
        
        self._build_ui()
        self._load_struct_definition()
    
    # ------------------------------------------------------------------ UI
    
    def _build_ui(self) -> None:
        layout = self.content_layout
        layout.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        layout.setSpacing(Sizes.SPACING_MEDIUM)
        
        self.header_label = QtWidgets.QLabel(self)
        self.header_label.setText("结构体条目")
        self.header_label.setStyleSheet(ThemeManager.heading(4))
        layout.addWidget(self.header_label)
        
        self.description_label = QtWidgets.QLabel(self)
        self.description_label.setText(
            "根据结构体定义编辑当前条目的各个字段，仅支持修改“字段值”列；"
            "列表/字典字段可以展开下方子表格进行详细编辑。"
        )
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet(ThemeManager.subtle_info_style())
        layout.addWidget(self.description_label)
        
        # 使用通用的两行结构字段表格组件承载字段值编辑
        self.fields_table_widget = TwoRowFieldTableWidget(
            get_all_variable_types(),
            parent=self,
            column_headers=("序号", "字段名", "数据类型", "字段值"),
        )
        layout.addWidget(self.fields_table_widget, 1)
    
    def _apply_styles(self) -> None:
        self.setStyleSheet(
            ThemeManager.dialog_surface_style(
                include_inputs=True,
                include_tables=True,
                include_scrollbars=True,
            )
        )

    # ------------------------------------------------------------------ 数据加载

    def _load_struct_definition(self) -> None:
        if not self._struct_id:
            self._set_empty_state("未选择结构体，无法加载字段列表。")
            return

        payload = get_struct_payload(self._struct_id)
        if not isinstance(payload, Mapping):
            self._set_empty_state(f"找不到结构体定义：{self._struct_id}")
            return

        name_value = payload.get("name")
        struct_name = (
            str(name_value).strip() if isinstance(name_value, str) else self._struct_id
        )
        if self._struct_id and self._struct_id != struct_name:
            display_name = f"{struct_name}（{self._struct_id}）"
        else:
            display_name = struct_name
        self.header_label.setText(display_name)

        value_entries = payload.get("value")
        if not isinstance(value_entries, Sequence):
            self._set_empty_state("结构体定义中未找到字段列表。")
            return

        fields_for_editor: List[Dict[str, Any]] = []
        for entry in value_entries:
            if not isinstance(entry, Mapping):
                continue
            raw_key = entry.get("key")
            raw_param_type = entry.get("param_type")
            field_name = str(raw_key).strip() if isinstance(raw_key, str) else ""
            param_type_text = (
                str(raw_param_type).strip() if isinstance(raw_param_type, str) else ""
            )
            if not field_name or not param_type_text:
                continue
            canonical_type = param_type_to_canonical(param_type_text)

            initial_raw_value = self._initial_values.get(field_name)
            fields_for_editor.append(
                {
                    "name": field_name,
                    "type_name": canonical_type,
                    "value": initial_raw_value,
                }
            )

        if not fields_for_editor:
            self._set_empty_state("结构体定义中未找到有效字段。")
            return

        self._apply_struct_id_options()
        self.fields_table_widget.load_fields(fields_for_editor)
        self._lock_field_name_and_type_columns()

    def _apply_struct_id_options(self) -> None:
        """为结构体/结构体列表字段提供可选的结构体 ID 列表。"""
        struct_ids_raw = list_struct_ids()
        if not isinstance(struct_ids_raw, Sequence):
            return

        struct_ids: List[str] = []
        for raw_id in struct_ids_raw:
            text = str(raw_id).strip()
            if text:
                struct_ids.append(text)

        if struct_ids:
            self.fields_table_widget.set_struct_id_options(struct_ids)

    def _lock_field_name_and_type_columns(self) -> None:
        """将字段名与类型列设为只读，仅允许修改数据值。"""
        table = self.fields_table_widget.table
        row_count = table.rowCount()
        row_index = 0
        while row_index < row_count:
            name_editor = self.fields_table_widget._get_cell_line_edit(row_index, 1)
            if isinstance(name_editor, QtWidgets.QLineEdit):
                name_editor.setReadOnly(True)
                name_editor.setStyleSheet(ThemeManager.readonly_input_style())

            type_combo = self.fields_table_widget._get_cell_combo_box(row_index, 2)
            if isinstance(type_combo, QtWidgets.QComboBox):
                type_combo.setEnabled(False)
                type_combo.setStyleSheet(ThemeManager.readonly_input_style())

            row_index += 2

    def _set_empty_state(self, message: str) -> None:
        self.header_label.setText(message)
        self.description_label.setText(
            "请返回上一层选择有效的结构体 ID 后再编辑条目。"
        )
        self.fields_table_widget.clear_fields()

    # ------------------------------------------------------------------ 确认与导出

    def validate(self) -> bool:
        result: Dict[str, Any] = {}
        fields = self.fields_table_widget.get_all_fields()
        for field in fields:
            field_name_value = field.get("name")
            field_name = (
                str(field_name_value).strip() if isinstance(field_name_value, str) else ""
            )
            if not field_name:
                continue
            result[field_name] = field.get("value")
        
        self._result = result
        return True

    def get_result(self) -> Dict[str, Any]:
        return dict(self._result)


__all__ = ["StructListItemEditDialog"]


