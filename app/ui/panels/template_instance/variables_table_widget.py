"""VariablesTab 专用的两行结构字段表格扩展。

从 variables_tab.py 中拆出，避免变量标签页文件职责过载。
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from PyQt6 import QtWidgets

from app.ui.dialogs.struct_definition_types import (
    normalize_canonical_type_name,
)
from app.ui.panels.template_instance.struct_list_editor_widget import StructListEditorWidget
from app.ui.widgets.two_row_field_table_widget import TwoRowFieldTableWidget


class VariablesTwoRowFieldTableWidget(TwoRowFieldTableWidget):
    """
    自定义变量标签页专用的两行结构字段表格。

    在保留列表/字典两行结构行为的基础上，为“结构体列表”类型提供专用的列表编辑组件，
    支持选择基础结构体并为每个条目配置字段值。
    """

    def __init__(
        self,
        supported_types: Sequence[str],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(supported_types, parent)
        self._resource_manager: Optional[object] = None

    def set_resource_manager(self, resource_manager: Optional[object]) -> None:
        self._resource_manager = resource_manager

    def _create_value_cell_widget(
        self,
        type_name: str,
        value: Any,
        readonly: bool = False,
    ) -> QtWidgets.QWidget:
        canonical_type_name = normalize_canonical_type_name(type_name or "")
        if canonical_type_name == "结构体列表":
            editor = StructListEditorWidget(
                struct_id_options=self._struct_id_options,
                resource_manager=self._resource_manager,
                value=value,
                parent=self.table,
            )
            editor.set_read_only(bool(readonly))
            editor.value_changed.connect(self._on_content_changed)
            return editor

        return super()._create_value_cell_widget(type_name, value, readonly)

    def _extract_value_from_widget(
        self,
        type_name: str,
        value_widget: Optional[QtWidgets.QWidget],
    ) -> Any:
        canonical_type_name = normalize_canonical_type_name(type_name or "")
        if canonical_type_name == "结构体列表":
            if isinstance(value_widget, StructListEditorWidget):
                return value_widget.get_value()
            if isinstance(value_widget, QtWidgets.QWidget):
                inner_editor = value_widget.findChild(StructListEditorWidget)
                if isinstance(inner_editor, StructListEditorWidget):
                    return inner_editor.get_value()
        return super()._extract_value_from_widget(type_name, value_widget)


__all__ = ["VariablesTwoRowFieldTableWidget"]


