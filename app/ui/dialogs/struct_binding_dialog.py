from __future__ import annotations

"""结构体绑定对话框

为结构体节点（拆分/拼装/修改）提供“选择结构体 + 选择字段”的轻量选择器。

输入为 `{struct_id: payload}` 字典（payload 为 STRUCT_DEFINITION 资源原始 JSON），
输出为 `(struct_id, [field_names])`。
"""

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from ui.foundation.base_widgets import BaseDialog
from ui.foundation.theme_manager import ThemeManager, Sizes
from ui.foundation import dialog_utils
from ui.dialogs.struct_definition_types import param_type_to_canonical, format_field_pairs_summary


class StructBindingDialog(BaseDialog):
    """结构体绑定对话框。

    - 左侧：结构体列表，仅展示名称；
    - 右侧：选中结构体的字段列表（带复选框），可多选字段；
    - 底部：确定 / 取消。
    """

    def __init__(
        self,
        *,
        structs: Dict[str, Mapping[str, object]],
        parent: Optional[QtWidgets.QWidget] = None,
        current_struct_id: str = "",
        current_field_names: Optional[Sequence[str]] = None,
    ) -> None:
        self._structs: Dict[str, Mapping[str, object]] = dict(structs)
        self._ordered_struct_ids: List[str] = []
        self._current_struct_id: str = str(current_struct_id or "")
        self._current_field_names: List[str] = (
            [name for name in current_field_names if isinstance(name, str) and name]
            if isinstance(current_field_names, Sequence) and not isinstance(current_field_names, (str, bytes))
            else []
        )
        
        self._selected_struct_id: str = ""
        self._selected_field_names: List[str] = []
        
        self.struct_list: QtWidgets.QListWidget
        self.field_list: QtWidgets.QListWidget

        super().__init__(
            title="配置结构体与字段",
            width=720,
            height=520,
            parent=parent,
        )
        
        self._build_content()
        self._populate_structs()
        self._restore_selection()

    # ------------------------------------------------------------------
    # UI 组装
    # ------------------------------------------------------------------

    def _build_content(self) -> None:
        layout = self.content_layout
        layout.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        layout.setSpacing(Sizes.SPACING_MEDIUM)

        info_label = QtWidgets.QLabel(
            "请选择要绑定的结构体，并勾选需要在当前节点中使用的字段。"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(ThemeManager.subtle_info_style())
        layout.addWidget(info_label)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self)

        # 左侧：结构体列表
        left_container = QtWidgets.QWidget(splitter)
        left_layout = QtWidgets.QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(Sizes.SPACING_SMALL)

        left_label = QtWidgets.QLabel("结构体")
        left_label.setStyleSheet(ThemeManager.heading(4))
        left_layout.addWidget(left_label)

        self.struct_list = QtWidgets.QListWidget(left_container)
        self.struct_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        left_layout.addWidget(self.struct_list, 1)

        # 右侧：字段列表
        right_container = QtWidgets.QWidget(splitter)
        right_layout = QtWidgets.QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(Sizes.SPACING_SMALL)

        right_label = QtWidgets.QLabel("字段列表")
        right_label.setStyleSheet(ThemeManager.heading(4))
        right_layout.addWidget(right_label)

        self.field_list = QtWidgets.QListWidget(right_container)
        self.field_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        right_layout.addWidget(self.field_list, 1)

        splitter.addWidget(left_container)
        splitter.addWidget(right_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter, 1)

        self.struct_list.currentRowChanged.connect(self._on_struct_selection_changed)

        self._apply_styles()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            ThemeManager.dialog_surface_style(
                include_inputs=True,
                include_tables=True,
                include_scrollbars=True,
            )
        )

    # ------------------------------------------------------------------
    # 数据填充与选择恢复
    # ------------------------------------------------------------------

    def _extract_struct_summary(self, struct_id: str, struct_data: Mapping[str, object]) -> Tuple[str, str]:
        """返回 (显示名, 字段摘要)"""
        name_value = struct_data.get("name")
        display_name = str(name_value).strip() if isinstance(name_value, str) else struct_id

        fields: List[Tuple[str, str]] = []
        value_entries = struct_data.get("value")
        if isinstance(value_entries, Sequence):
            for entry in value_entries:
                if not isinstance(entry, Mapping):
                    continue
                raw_key = entry.get("key")
                raw_param_type = entry.get("param_type")
                field_name = str(raw_key).strip() if isinstance(raw_key, str) else ""
                param_type = str(raw_param_type).strip() if isinstance(raw_param_type, str) else ""
                if not field_name or not param_type:
                    continue
                canonical_type = param_type_to_canonical(param_type)
                fields.append((field_name, canonical_type))
        summary = format_field_pairs_summary(fields)
        return display_name, summary

    def _populate_structs(self) -> None:
        self.struct_list.clear()
        struct_items: List[Tuple[str, str, str]] = []

        for struct_id, data in self._structs.items():
            if not isinstance(data, Mapping):
                continue
            display_name, summary = self._extract_struct_summary(struct_id, data)
            struct_items.append((struct_id, display_name, summary))

        # 按名称排序
        struct_items.sort(key=lambda item: item[1])
        self._ordered_struct_ids = [item[0] for item in struct_items]

        for struct_id, display_name, summary in struct_items:
            item = QtWidgets.QListWidgetItem(display_name, self.struct_list)
            tooltip_parts: List[str] = [f"ID: {struct_id}"]
            if summary:
                tooltip_parts.append(summary)
            item.setToolTip("\n".join(tooltip_parts))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, struct_id)

    def _restore_selection(self) -> None:
        """尝试根据已有绑定恢复结构体与字段勾选。"""
        if not self._ordered_struct_ids:
            return

        # 恢复结构体选中
        target_struct_id = self._current_struct_id or self._ordered_struct_ids[0]
        target_row = -1
        for row in range(self.struct_list.count()):
            item = self.struct_list.item(row)
            if not isinstance(item, QtWidgets.QListWidgetItem):
                continue
            struct_id_value = item.data(QtCore.Qt.ItemDataRole.UserRole)
            struct_id = str(struct_id_value) if struct_id_value is not None else ""
            if struct_id == target_struct_id:
                target_row = row
                break

        if target_row >= 0:
            self.struct_list.setCurrentRow(target_row)
        else:
            self.struct_list.setCurrentRow(0)

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_struct_selection_changed(self, row: int) -> None:
        """当左侧结构体选中行变化时，刷新右侧字段列表。"""
        if row < 0 or row >= self.struct_list.count():
            self.field_list.clear()
            return

        item = self.struct_list.item(row)
        if not isinstance(item, QtWidgets.QListWidgetItem):
            self.field_list.clear()
            return

        struct_id_value = item.data(QtCore.Qt.ItemDataRole.UserRole)
        struct_id = str(struct_id_value) if struct_id_value is not None else ""
        if not struct_id or struct_id not in self._structs:
            self.field_list.clear()
            return

        struct_data = self._structs[struct_id]
        self._populate_fields_for_struct(struct_id, struct_data)

    def _populate_fields_for_struct(self, struct_id: str, struct_data: Mapping[str, object]) -> None:
        """根据给定结构体数据填充字段列表。"""
        self.field_list.clear()

        value_entries = struct_data.get("value")
        if not isinstance(value_entries, Sequence):
            return

        existing_selected: List[str] = []
        if struct_id == self._current_struct_id and self._current_field_names:
            existing_selected = list(self._current_field_names)

        for entry in value_entries:
            if not isinstance(entry, Mapping):
                continue
            raw_name = entry.get("key")
            raw_param_type = entry.get("param_type")
            field_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
            param_type = str(raw_param_type).strip() if isinstance(raw_param_type, str) else ""
            if not field_name or not param_type:
                continue

            canonical_type = param_type_to_canonical(param_type)
            display_text = f"{field_name}（{canonical_type}）"

            item = QtWidgets.QListWidgetItem(display_text, self.field_list)
            item.setFlags(
                QtCore.Qt.ItemFlag.ItemIsEnabled
                | QtCore.Qt.ItemFlag.ItemIsSelectable
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setData(QtCore.Qt.ItemDataRole.UserRole, field_name)

            if field_name in existing_selected or not existing_selected:
                item.setCheckState(QtCore.Qt.CheckState.Checked)
            else:
                item.setCheckState(QtCore.Qt.CheckState.Unchecked)

    def validate(self) -> bool:
        """点击确定按钮时读取当前结构体与字段选择。"""
        struct_id = self._current_struct_selection()
        if not struct_id:
            dialog_utils.show_warning_dialog(self, "警告", "请先选择一个结构体")
            return False
        
        field_names = self._current_checked_fields()
        if not field_names:
            dialog_utils.show_warning_dialog(self, "警告", "请至少勾选一个字段")
            return False
        
        self._selected_struct_id = struct_id
        self._selected_field_names = field_names
        return True

    # ------------------------------------------------------------------
    # 辅助方法：读取当前选择
    # ------------------------------------------------------------------

    def _current_struct_selection(self) -> str:
        row = self.struct_list.currentRow()
        if row < 0:
            return ""
        item = self.struct_list.item(row)
        if not isinstance(item, QtWidgets.QListWidgetItem):
            return ""
        struct_id_value = item.data(QtCore.Qt.ItemDataRole.UserRole)
        struct_id = str(struct_id_value) if struct_id_value is not None else ""
        return struct_id

    def _current_checked_fields(self) -> List[str]:
        names: List[str] = []
        for index in range(self.field_list.count()):
            item = self.field_list.item(index)
            if not isinstance(item, QtWidgets.QListWidgetItem):
                continue
            if item.checkState() != QtCore.Qt.CheckState.Checked:
                continue
            field_name_value = item.data(QtCore.Qt.ItemDataRole.UserRole)
            field_name = str(field_name_value) if field_name_value is not None else ""
            if field_name:
                names.append(field_name)
        return names

    # ------------------------------------------------------------------
    # 对外结果
    # ------------------------------------------------------------------

    def get_result(self) -> Tuple[str, List[str]]:
        """返回 (struct_id, [field_names])。"""
        return self._selected_struct_id, list(self._selected_field_names)


__all__ = ["StructBindingDialog"]


