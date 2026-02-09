from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .management_sections_base import *


class VariableSection(BaseManagementSection):
    """关卡变量管理 Section（对应 `ManagementData.level_variables`）。"""

    section_key = "variable"
    tree_label = "📊 关卡变量"
    type_name = "关卡变量模板"
    _usage_text: str = ""

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        from engine.resources.level_variable_schema_view import (
            get_default_level_variable_schema_view,
        )

        schema_view = get_default_level_variable_schema_view()
        grouped_variables = self._group_variables_by_file_id(package)

        for file_id, entries in grouped_variables.items():
            file_info = schema_view.get_variable_file(file_id)
            display_name = file_info.file_name if file_info is not None else file_id
            source_display = (
                self._build_source_display(file_info.source_path)
                if file_info is not None
                else ""
            )
            preview_names = [self._get_variable_display_name(var_id, payload) for var_id, payload in entries]
            preview_text = ", ".join(preview_names[:3])
            attr1_text = f"变量数量: {len(entries)}"
            attr2_text = f"示例: {preview_text}" if preview_text else ""
            attr3_text = f"来源: {source_display}" if source_display else f"文件ID: {file_id}"
            last_modified_value = self._get_latest_last_modified(entries)
            yield ManagementRowData(
                name=display_name,
                type_name=self.type_name,
                attr1=attr1_text,
                attr2=attr2_text,
                attr3=attr3_text,
                description="按文件聚合的关卡变量模板（只读）",
                last_modified=last_modified_value,
                user_data=(self.section_key, file_id),
            )

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        _ = (parent_widget, title, initial)
        return None

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = (parent_widget, package)
        return False

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        _ = (parent_widget, package, item_id)
        return False

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        _ = (package, item_id)
        return False

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        from engine.resources.level_variable_schema_view import (
            get_default_level_variable_schema_view,
        )

        schema_view = get_default_level_variable_schema_view()
        grouped_variables = self._group_variables_by_file_id(package)
        entries = grouped_variables.get(item_id)
        if entries is None:
            return None

        file_info = schema_view.get_variable_file(item_id)
        source_display_name = (
            self._build_source_display(file_info.source_path)
            if file_info is not None
            else item_id
        )
        file_name_display = file_info.file_name if file_info is not None else item_id

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            if self._usage_text:
                usage_label = QtWidgets.QLabel(self._usage_text, parent)
                usage_label.setWordWrap(True)
                form_layout.addRow("使用情况", usage_label)

            file_id_label = QtWidgets.QLabel(str(item_id), parent)
            form_layout.addRow("文件ID", file_id_label)

            file_name_label = QtWidgets.QLabel(str(file_name_display), parent)
            form_layout.addRow("显示名", file_name_label)

            source_label = QtWidgets.QLabel(source_display_name, parent)
            form_layout.addRow("源文件", source_label)

            table = QtWidgets.QTableWidget(len(entries), 6, parent)
            table.setHorizontalHeaderLabels(
                ["变量ID", "变量名称", "类型", "默认值", "全局", "描述"]
            )
            table.setWordWrap(True)
            table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
            table.setAlternatingRowColors(True)
            table.horizontalHeader().setStretchLastSection(True)
            table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            table.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Maximum,
            )

            for row_index, (variable_id, payload) in enumerate(entries):
                name_text = self._get_variable_display_name(variable_id, payload)
                type_text = str(payload.get("variable_type", ""))
                default_value_text = self._format_default_value(payload.get("default_value"))
                is_global_value = "是" if bool(payload.get("is_global", True)) else "否"
                description_text = str(payload.get("description", ""))

                table.setItem(row_index, 0, QtWidgets.QTableWidgetItem(variable_id))
                table.setItem(row_index, 1, QtWidgets.QTableWidgetItem(name_text))
                table.setItem(row_index, 2, QtWidgets.QTableWidgetItem(type_text))
                table.setItem(row_index, 3, QtWidgets.QTableWidgetItem(default_value_text))
                table.setItem(row_index, 4, QtWidgets.QTableWidgetItem(is_global_value))
                table.setItem(row_index, 5, QtWidgets.QTableWidgetItem(description_text))

            header = table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.Stretch)

            table.resizeColumnsToContents()
            table.resizeRowsToContents()

            section_label = QtWidgets.QLabel("变量列表", parent)
            section_label.setStyleSheet("font-weight: 600;")
            form_layout.addRow(section_label)
            form_layout.addRow(table)

        title = f"变量模板：{file_name_display}"
        description = "按源文件聚合的关卡变量列表（代码级只读视图）。"
        _ = on_changed
        return title, description, build_form

    def set_usage_text(self, usage_text: str) -> None:
        self._usage_text = usage_text

    @staticmethod
    def _get_source_key(payload: Dict[str, Any]) -> str:
        source_candidates: List[str] = []
        source_path_value = payload.get("source_path")
        if isinstance(source_path_value, str):
            source_candidates.append(source_path_value.strip())

        metadata_value = payload.get("metadata", {})
        if isinstance(metadata_value, dict):
            metadata_source = metadata_value.get("source_path")
            if isinstance(metadata_source, str):
                source_candidates.append(metadata_source.strip())

        source_file_value = payload.get("source_file")
        if isinstance(source_file_value, str):
            source_candidates.append(source_file_value.strip())

        for candidate in source_candidates:
            if candidate:
                return candidate
        return "未标注来源"

    def _group_variables_by_file_id(
        self,
        package: ManagementPackage,
    ) -> OrderedDict[str, List[Tuple[str, Dict[str, Any]]]]:
        variables_mapping = getattr(package.management, "level_variables", {}) or {}
        grouped: OrderedDict[str, List[Tuple[str, Dict[str, Any]]]] = OrderedDict()

        for variable_id, payload_any in variables_mapping.items():
            if not isinstance(payload_any, dict):
                continue
            file_id_value = payload_any.get("variable_file_id")
            group_id = (
                file_id_value.strip()
                if isinstance(file_id_value, str) and file_id_value.strip()
                else self._get_source_key(payload_any)
            )
            if group_id not in grouped:
                grouped[group_id] = []
            grouped[group_id].append((variable_id, payload_any))

        return grouped

    @staticmethod
    def _get_variable_display_name(variable_id: str, payload: Dict[str, Any]) -> str:
        name_value = payload.get("variable_name") or payload.get("name") or variable_id
        return str(name_value)

    @staticmethod
    def _build_source_display(source_key: str) -> str:
        path_obj = Path(source_key)
        if path_obj.suffix:
            return path_obj.with_suffix("").as_posix()
        return source_key

    def _get_latest_last_modified(
        self, entries: List[Tuple[str, Dict[str, Any]]]
    ) -> str:
        latest_value = ""
        for _, payload in entries:
            candidate = self._get_last_modified_text(payload)
            if candidate and candidate > latest_value:
                latest_value = candidate
        return latest_value

    @staticmethod
    def _format_default_value(value: Any) -> str:
        if value is None:
            return ""
        text = repr(value)
        if len(text) > 120:
            return f"{text[:117]}..."
        return text



