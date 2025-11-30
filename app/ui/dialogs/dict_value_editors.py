from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from ui.dialogs.table_edit_helpers import wrap_click_to_edit_line_edit_for_table_cell
from ui.dialogs.value_editor_common_widgets import ClickToEditLineEdit, ScrollSafeComboBox
from ui.dialogs.list_value_editors import ListValueEditor
from ui.dialogs.struct_definition_types import normalize_canonical_type_name, is_list_type
from ui.foundation.base_widgets import BaseDialog
from ui.foundation.context_menu_builder import ContextMenuBuilder
from ui.foundation.theme_manager import Sizes, ThemeManager, Icons as ThemeIcons, Colors


class _DictTableEditorWidget(QtWidgets.QWidget):
    """封装“序号 + 键 + 值”三列表格及“添加/删除条目”工具栏的基础组件。

    - `DictValueEditor` 与 `DictEditDialog` 复用此组件，统一列宽策略、行高和占位文案。
    - 通过 `use_click_to_edit_line_edit` 控制是否使用 `ClickToEditLineEdit` + 包裹容器，
      以适配内联编辑与弹窗编辑时不同的焦点与误触需求。
    """

    entries_changed = QtCore.pyqtSignal()

    def __init__(
        self,
        *,
        key_placeholder_text: str,
        value_placeholder_text: str,
        use_click_to_edit_line_edit: bool,
        value_is_list_type: bool = False,
        initial_entries: Optional[Sequence[Tuple[str, str]]] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._key_placeholder_text = key_placeholder_text
        self._value_placeholder_text = value_placeholder_text
        self._use_click_to_edit_line_edit = use_click_to_edit_line_edit
        self._value_is_list_type: bool = value_is_list_type
        self._entries: List[Tuple[str, str]] = []
        self._is_read_only: bool = False

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(Sizes.SPACING_SMALL)

        toolbar_layout = QtWidgets.QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(Sizes.SPACING_SMALL)
        self.add_button = QtWidgets.QPushButton(self)
        self.add_button.setText("＋ 新增")
        self.remove_button = QtWidgets.QPushButton(self)
        self.remove_button.setText("－ 删除")
        # 字典子表格的新增/删除入口整体收敛到“尾部空白行 + 行级右键菜单”中，
        # 这里保留按钮对象以兼容外部只读逻辑，但不再在 UI 中展示独立工具栏按钮。
        self.add_button.setVisible(False)
        self.remove_button.setVisible(False)
        toolbar_layout.addStretch()
        root_layout.addLayout(toolbar_layout)

        self.table = QtWidgets.QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["序号", "键", "值"])
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(
                0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(
                1, QtWidgets.QHeaderView.ResizeMode.Stretch
            )
            header.setSectionResizeMode(
                2, QtWidgets.QHeaderView.ResizeMode.Stretch
            )
        vertical_header = self.table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
            default_row_height = Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL
            vertical_header.setDefaultSectionSize(default_row_height)
        # 使用按像素滚动，避免当字典条目或值列表较多时，每次滚轮滚动跨越过多内容。
        self.table.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        root_layout.addWidget(self.table)

        # 为子表格行定制右键菜单：仅提供“删除当前行”，禁用原生菜单。
        self.table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)

        self.add_button.clicked.connect(self._on_add_clicked)
        self.remove_button.clicked.connect(self._on_remove_clicked)

        if initial_entries:
            for key_text, value_text in initial_entries:
                self._add_row(key_text, value_text)
        if self.table.rowCount() == 0:
            self._add_row("", "")
        # 确保始终在末尾保留一个空白占位行，便于快速新增字典条目（只读模式下不会附加该占位行）。
        self._ensure_trailing_placeholder_row()
        self._collect_entries()
        self._update_table_height()

    def set_entries(self, entries: Sequence[Tuple[str, str]]) -> None:
        self.table.setRowCount(0)
        self._entries = []
        for key_text, value_text in entries:
            self._add_row(key_text, value_text)
        if self.table.rowCount() == 0:
            self._add_row("", "")
        self._ensure_trailing_placeholder_row()
        self._collect_entries()
        self._update_table_height()
        self.entries_changed.emit()

    def get_entries(self) -> List[Tuple[str, str]]:
        self._collect_entries()
        return list(self._entries)

    def _create_key_editor_widget(self, key_text: str) -> QtWidgets.QWidget:
        if self._use_click_to_edit_line_edit:
            line_edit = ClickToEditLineEdit(key_text, self.table)
            line_edit.setPlaceholderText(self._key_placeholder_text)
            line_edit.setClearButtonEnabled(True)
            line_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
            line_edit.editingFinished.connect(self._on_entries_edited)
            return wrap_click_to_edit_line_edit_for_table_cell(self.table, line_edit)

        line_edit = QtWidgets.QLineEdit(key_text, self.table)
        line_edit.setPlaceholderText(self._key_placeholder_text)
        line_edit.setClearButtonEnabled(True)
        line_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        line_edit.editingFinished.connect(self._on_entries_edited)
        return line_edit

    def _create_value_editor_widget(self, value_text: str) -> QtWidgets.QWidget:
        """根据当前值类型创建“值”列编辑控件。

        - 普通标量：使用单行文本编辑；
        - 当值类型为列表时：使用内联 ListValueEditor 展示/编辑元素集合。
        """
        # 值类型为列表时，使用内联列表编辑器
        if self._value_is_list_type:
            initial_values: List[str] = []
            text = (value_text or "").strip()
            if text:
                # 简单按逗号分隔的形式拆分，避免在 UI 层使用 ast 解析表达式。
                parts = [part.strip() for part in text.split(",")]
                initial_values = [p for p in parts if p]

            editor = ListValueEditor(
                element_type_name="字符串",
                values=initial_values,
                parent=self.table,
                enable_collapse=False,
            )
            editor.value_changed.connect(self._on_entries_edited)
            return editor

        # 普通标量仍使用“点击才能编辑”的单行文本框
        if self._use_click_to_edit_line_edit:
            line_edit = ClickToEditLineEdit(value_text, self.table)
            line_edit.setPlaceholderText(self._value_placeholder_text)
            line_edit.setClearButtonEnabled(True)
            line_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
            line_edit.editingFinished.connect(self._on_entries_edited)
            return wrap_click_to_edit_line_edit_for_table_cell(self.table, line_edit)

        line_edit = QtWidgets.QLineEdit(value_text, self.table)
        line_edit.setPlaceholderText(self._value_placeholder_text)
        line_edit.setClearButtonEnabled(True)
        line_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        line_edit.editingFinished.connect(self._on_entries_edited)
        return line_edit

    def _add_row(self, key_text: str, value_text: str) -> None:
        row_index = self.table.rowCount()
        self.table.insertRow(row_index)

        index_item = QtWidgets.QTableWidgetItem(str(row_index + 1))
        index_item.setFlags(
            QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled
        )
        self.table.setItem(row_index, 0, index_item)

        key_widget = self._create_key_editor_widget(key_text)
        self.table.setCellWidget(row_index, 1, key_widget)

        value_widget = self._create_value_editor_widget(value_text)
        self.table.setCellWidget(row_index, 2, value_widget)
        self._update_table_height()

    def _refresh_indices(self) -> None:
        for row_index in range(self.table.rowCount()):
            index_item = self.table.item(row_index, 0)
            if index_item is None:
                index_item = QtWidgets.QTableWidgetItem()
                index_item.setFlags(
                    QtCore.Qt.ItemFlag.ItemIsSelectable
                    | QtCore.Qt.ItemFlag.ItemIsEnabled
                )
                self.table.setItem(row_index, 0, index_item)
            index_item.setText(str(row_index + 1))

    def _extract_text_from_cell_widget(
        self, widget: Optional[QtWidgets.QWidget]
    ) -> str:
        # 列表值：从内联 ListValueEditor 中提取元素列表，并序列化为逗号分隔字符串
        if isinstance(widget, ListValueEditor):
            values = widget.get_values()
            return ", ".join(values)
        if isinstance(widget, QtWidgets.QWidget):
            inner_list = widget.findChild(ListValueEditor)
            if isinstance(inner_list, ListValueEditor):
                values = inner_list.get_values()
                return ", ".join(values)

        # 标量值：按原有逻辑从 QLineEdit 中取文本
        if isinstance(widget, QtWidgets.QLineEdit):
            return widget.text()
        if isinstance(widget, QtWidgets.QWidget):
            inner_edit = widget.findChild(QtWidgets.QLineEdit)
            if isinstance(inner_edit, QtWidgets.QLineEdit):
                return inner_edit.text()
        return ""

    def _collect_entries(self) -> List[Tuple[str, str]]:
        collected_entries: List[Tuple[str, str]] = []
        for row_index in range(self.table.rowCount()):
            key_widget = self.table.cellWidget(row_index, 1)
            value_widget = self.table.cellWidget(row_index, 2)
            key_text = self._extract_text_from_cell_widget(key_widget)
            value_text = self._extract_text_from_cell_widget(value_widget)
            if key_text or value_text:
                collected_entries.append((key_text, value_text))
        self._entries = collected_entries
        return collected_entries

    def _on_add_clicked(self) -> None:
        self._add_row("", "")
        self._refresh_indices()
        self._collect_entries()
        self._ensure_trailing_placeholder_row()
        self._update_table_height()
        self.entries_changed.emit()

    def _on_remove_clicked(self) -> None:
        current_row_index = self.table.currentRow()
        if current_row_index < 0:
            return
        self.table.removeRow(current_row_index)
        self._refresh_indices()
        self._collect_entries()
        self._ensure_trailing_placeholder_row()
        self._update_table_height()
        self.entries_changed.emit()

    def _on_entries_edited(self) -> None:
        self._collect_entries()
        self._ensure_trailing_placeholder_row()
        self.entries_changed.emit()
        self._update_table_height()

    def debug_print_heights(self) -> None:
        """调试辅助：打印当前字典子表格的高度信息。"""
        header = self.table.horizontalHeader()
        vertical_header = self.table.verticalHeader()
        default_row_height = Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL

        if vertical_header is not None:
            rows_height = vertical_header.length()
        else:
            row_count = max(self.table.rowCount(), 1)
            rows_height = default_row_height * row_count

        header_height = header.height() if header is not None else default_row_height
        total_height = header_height + rows_height + Sizes.PADDING_SMALL * 2

        print(
            "[UI调试/DictValueEditor]",
            f"条目数={self.table.rowCount()}",
            f"header_height={header_height}",
            f"rows_height={rows_height}",
            f"total_height={total_height}",
            f"table.sizeHint={self.table.sizeHint()}",
        )

    def _update_table_height(self) -> None:
        """根据当前行数调整字典子表格高度，尽量让所有条目完整展示。"""
        header = self.table.horizontalHeader()
        vertical_header = self.table.verticalHeader()
        default_row_height = Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL

        # 先根据单元格内容自动调整每一行高度，尤其是当“值”列为内联 ListValueEditor 时，
        # 避免子列表被当前行默认高度裁剪。
        self.table.resizeRowsToContents()

        if vertical_header is not None:
            rows_height = vertical_header.length()
        else:
            row_count = max(self.table.rowCount(), 1)
            rows_height = default_row_height * row_count

        header_height = header.height() if header is not None else default_row_height
        extra_margins = Sizes.PADDING_SMALL * 2

        total_height = header_height + rows_height + extra_margins
        total_height = max(total_height, default_row_height * 2)

        self.table.setMinimumHeight(total_height)
        self.table.setMaximumHeight(total_height)

    def _ensure_trailing_placeholder_row(self) -> None:
        """确保字典子表格末尾始终保留一个空白占位行，用于快速新增条目。"""
        if self._is_read_only:
            return
        row_count = self.table.rowCount()
        if row_count == 0:
            self._add_row("", "")
            return
        last_row_index = row_count - 1
        key_widget = self.table.cellWidget(last_row_index, 1)
        value_widget = self.table.cellWidget(last_row_index, 2)
        key_text = self._extract_text_from_cell_widget(key_widget)
        value_text = self._extract_text_from_cell_widget(value_widget)
        if key_text.strip() or value_text.strip():
            self._add_row("", "")

    def set_read_only(self, read_only: bool) -> None:
        """切换字典子表格的只读状态。

        只读模式下移除尾部用于新增的空白占位行，防止在不可保存视图中出现伪“新建”入口。
        """
        self._is_read_only = bool(read_only)
        if not self._is_read_only:
            return

        row_count = self.table.rowCount()
        if row_count <= 0:
            return

        last_row_index = row_count - 1
        self.table.removeRow(last_row_index)
        self._refresh_indices()
        self._update_table_height()

    def _on_table_context_menu(self, pos: QtCore.QPoint) -> None:
        index = self.table.indexAt(pos)
        row_index = index.row()
        if row_index < 0:
            return

        def delete_current_row() -> None:
            self.table.removeRow(row_index)
            self._refresh_indices()
            self._collect_entries()
            self._ensure_trailing_placeholder_row()
            self._update_table_height()
            self.entries_changed.emit()

        builder = ContextMenuBuilder(self.table)
        builder.add_action("删除当前行", delete_current_row)
        builder.exec_for(self.table.viewport(), pos)


class DictValueEditor(QtWidgets.QWidget):
    """字典类型字段的“数据值”单元格：内联子表格编辑，展示键和值。

    在字段行内部直接展示键值对集合，并提供键/值类型下拉框。
    """

    value_changed = QtCore.pyqtSignal()

    def __init__(
        self,
        key_type_name: str,
        value_type_name: str,
        entries: Sequence[Tuple[str, str]],
        *,
        base_type_options: Sequence[str],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        base_type_list: List[str] = list(base_type_options)
        if not base_type_list:
            base_type_list.append("字符串")
        self._base_type_options: List[str] = base_type_list
        self._is_collapsed: bool = False
        self._header_detached: bool = False

        default_type = self._base_type_options[0]
        initial_key_type = key_type_name or default_type
        initial_value_type = value_type_name or default_type

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(Sizes.SPACING_SMALL)
        self._root_layout = root_layout

        # 顶部摘要区：折叠按钮 + 条目摘要，仅用于在字段主行中展示。
        self._summary_container = QtWidgets.QWidget(self)
        summary_layout = QtWidgets.QHBoxLayout(self._summary_container)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(Sizes.SPACING_SMALL)

        self.collapse_button = QtWidgets.QToolButton(self)
        self.collapse_button.setCheckable(True)
        self.collapse_button.setChecked(False)
        self.collapse_button.setText(ThemeIcons.CHEVRON_DOWN)
        self.collapse_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self.collapse_button.clicked.connect(self._on_toggle_collapsed)

        self.summary_label = QtWidgets.QLabel(self)
        self.summary_label.setStyleSheet(ThemeManager.subtle_info_style())
        summary_layout.addWidget(self.collapse_button)
        summary_layout.addWidget(self.summary_label)
        summary_layout.addStretch()
        root_layout.addWidget(self._summary_container)

        # 键/值类型选择区：放在子表格上方，并让“键类型 / 值类型”各自出现在对应列的正上方。
        # 这里使用二维网格布局：
        # - 第 0 列为序号列预留缩进；
        # - 第 1 列摆放“键类型”标签与下拉框；
        # - 第 2 列摆放“值类型”标签与下拉框。
        types_layout = QtWidgets.QGridLayout()
        types_layout.setContentsMargins(0, 0, 0, 0)
        types_layout.setHorizontalSpacing(Sizes.SPACING_SMALL)
        types_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        key_type_label = QtWidgets.QLabel("键", self)
        self.key_type_combo = ScrollSafeComboBox(self)
        self.key_type_combo.addItems(self._base_type_options)
        self.key_type_combo.setCurrentText(initial_key_type)
        self.key_type_combo.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.key_type_combo.setMinimumWidth(120)

        value_type_label = QtWidgets.QLabel("值", self)
        self.value_type_combo = ScrollSafeComboBox(self)
        self.value_type_combo.addItems(self._base_type_options)
        self.value_type_combo.setCurrentText(initial_value_type)
        self.value_type_combo.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.value_type_combo.setMinimumWidth(120)

        # 第 0 列：为“序号”列预留缩进，不放实际控件，只占两行高度；
        # 第 1 列：键类型（上方是标签，下方是下拉框）；
        # 第 2 列：值类型（上方是标签，下方是下拉框）。
        spacer_for_index = QtWidgets.QSpacerItem(
            0,
            Sizes.INPUT_HEIGHT,
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        types_layout.addItem(spacer_for_index, 0, 0, 2, 1)
        types_layout.addWidget(key_type_label, 0, 1)
        types_layout.addWidget(self.key_type_combo, 1, 1)
        types_layout.addWidget(value_type_label, 0, 2)
        types_layout.addWidget(self.value_type_combo, 1, 2)
        types_layout.setColumnStretch(1, 1)
        types_layout.setColumnStretch(2, 1)
        root_layout.addLayout(types_layout)

        # 内联子表格：序号 + 键 + 值
        canonical_value_type = normalize_canonical_type_name(value_type_name or "")
        value_is_list_type = is_list_type(canonical_value_type)
        self._table_editor = _DictTableEditorWidget(
            key_placeholder_text="键",
            value_placeholder_text="值",
            use_click_to_edit_line_edit=True,
            value_is_list_type=value_is_list_type,
            initial_entries=list(entries),
            parent=self,
        )
        root_layout.addWidget(self._table_editor)

        # 暴露底层表格与按钮，方便上层在极少数情况下直接自定义行为。
        self.table = self._table_editor.table
        self.add_button = self._table_editor.add_button
        self.remove_button = self._table_editor.remove_button

        self._table_editor.entries_changed.connect(self._on_entries_changed)
        self.key_type_combo.currentTextChanged.connect(self._on_type_changed)
        self.value_type_combo.currentTextChanged.connect(self._on_type_changed)

        # 为嵌入单元格的字典编辑器提供基础高度
        self.setMinimumHeight((Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL) * 2)
        self._update_summary_text()

        # 默认折叠字典详情，先展示紧凑的“折叠 + 摘要”视图，避免大数据量时初始展开造成卡顿。
        self._on_toggle_collapsed()

    def set_read_only(self, read_only: bool) -> None:
        """切换字典值编辑器的只读状态。

        当前主要用于结构体等场景的“只读预览”模式：上层不再允许写回时，移除尾部用于新增的空白占位行，
        避免给用户造成可以在 UI 中新增条目的错觉；键/值类型与现有条目本身的只读与否仍交由上层控制。
        """
        self._table_editor.set_read_only(read_only)

    def create_header_proxy(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """将“折叠按钮 + 条目摘要”抽离到外层表格的主行中。

        默认情况下，DictValueEditor 自己持有顶部“折叠 + N 条目”这一行。
        当结构体编辑器希望在字段主行展示折叠控制与摘要时，会调用本方法：
        - 从自身垂直布局中移除摘要容器
        - 将其重新挂载到外部提供的 parent 上
        - 内部仅保留“键/值类型选择 + 子表格 + 添加/删除条目工具栏”作为详情行内容
        """
        if self._header_detached:
            return self._summary_container
        self._header_detached = True

        layout = self.layout()
        if isinstance(layout, QtWidgets.QVBoxLayout):
            layout.removeWidget(self._summary_container)

        self._summary_container.setParent(parent)
        return self._summary_container

    def _update_summary_text(self) -> None:
        entries = self._table_editor.get_entries()
        entry_count = len(entries)
        if entry_count == 0:
            summary_text = "0 条目"
        elif entry_count == 1:
            summary_text = "1 条目"
        else:
            summary_text = f"{entry_count} 条目"
        self.summary_label.setText(summary_text)

    def _on_entries_changed(self) -> None:
        self._update_summary_text()
        self.value_changed.emit()

    def _on_type_changed(self, _new_text: str) -> None:
        self._update_summary_text()
        self.value_changed.emit()

    def _on_toggle_collapsed(self) -> None:
        self._is_collapsed = not self._is_collapsed
        is_visible = not self._is_collapsed
        # 折叠时仅隐藏子表格与工具栏，保留主行中的折叠控制与摘要。
        self._table_editor.setVisible(is_visible)
        self.collapse_button.setText(
            ThemeIcons.CHEVRON_RIGHT if self._is_collapsed else ThemeIcons.CHEVRON_DOWN
        )
        if self._is_collapsed:
            collapsed_color = ThemeManager.Colors.TEXT_DISABLED
            self.collapse_button.setStyleSheet(
                f"QToolButton {{ color: {collapsed_color}; }}"
            )
        else:
            self.collapse_button.setStyleSheet("")
        self.updateGeometry()
        self.value_changed.emit()

        # 展开时输出高度调试信息，便于检查父表格行高是否充足
        if is_visible:
            self._table_editor._update_table_height()
            self._table_editor.debug_print_heights()

    def is_collapsed(self) -> bool:
        return self._is_collapsed

    def get_dict_state(self) -> dict:
        key_type_name = self.key_type_combo.currentText().strip()
        value_type_name = self.value_type_combo.currentText().strip()
        if not key_type_name:
            key_type_name = self._base_type_options[0]
        if not value_type_name:
            value_type_name = self._base_type_options[0]
        entries = self._table_editor.get_entries()
        return {
            "key_type_name": key_type_name,
            "value_type_name": value_type_name,
            "entries": entries,
        }
        
        
class DictEditDialog(BaseDialog):
    """编辑字典值的对话框。"""
    
    def __init__(
        self,
        *,
        key_type_name: str,
        value_type_name: str,
        entries: Sequence[Tuple[str, str]],
        base_type_options: Sequence[str],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        self._base_type_options: List[str] = list(base_type_options)
        if self._base_type_options:
            default_type = self._base_type_options[0]
        else:
            default_type = "字符串"
        self._key_type_name = key_type_name or default_type
        self._value_type_name = value_type_name or default_type
        self._entries: List[Tuple[str, str]] = list(entries)
        
        super().__init__(
            title="编辑字典",
            width=520,
            height=420,
            parent=parent,
        )
        
        self._build_content()
    
    def _build_content(self) -> None:
        layout = self.content_layout
        layout.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        layout.setSpacing(Sizes.SPACING_MEDIUM)
        
        form_layout = QtWidgets.QFormLayout()
        form_layout.setLabelAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        form_layout.setFormAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignTop
        )
        form_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)
        
        self.key_type_combo = QtWidgets.QComboBox(self)
        self.key_type_combo.addItems(self._base_type_options)
        self.key_type_combo.setCurrentText(self._key_type_name)
        form_layout.addRow("键类型:", self.key_type_combo)
        
        self.value_type_combo = QtWidgets.QComboBox(self)
        self.value_type_combo.addItems(self._base_type_options)
        self.value_type_combo.setCurrentText(self._value_type_name)
        form_layout.addRow("值类型:", self.value_type_combo)
        
        layout.addLayout(form_layout)
        
        canonical_value_type = normalize_canonical_type_name(self._value_type_name or "")
        value_is_list_type = is_list_type(canonical_value_type)
        self._table_editor = _DictTableEditorWidget(
            key_placeholder_text="键",
            value_placeholder_text="值",
            use_click_to_edit_line_edit=False,
            value_is_list_type=value_is_list_type,
            initial_entries=self._entries,
            parent=self,
        )
        layout.addWidget(self._table_editor)
        
        self.table = self._table_editor.table
        self.add_button = self._table_editor.add_button
        self.remove_button = self._table_editor.remove_button
        
        # 单击单元格时自动聚焦到内部编辑控件
        self.table.cellClicked.connect(self._focus_cell_widget)
    
    def _apply_styles(self) -> None:
        self.setStyleSheet(
            ThemeManager.dialog_surface_style(
                include_inputs=True,
                include_tables=True,
                include_scrollbars=True,
            )
        )
    
    def _focus_cell_widget(self, row: int, column: int) -> None:
        widget = self.table.cellWidget(row, column)
        if isinstance(widget, QtWidgets.QLineEdit):
            widget.setFocus()
    
    def validate(self) -> bool:
        self._key_type_name = self.key_type_combo.currentText().strip()
        self._value_type_name = self.value_type_combo.currentText().strip()
        self._entries = self._table_editor.get_entries()
        return True
    
    def get_dict_state(self) -> dict:
        return {
            "key_type_name": self._key_type_name,
            "value_type_name": self._value_type_name,
            "entries": list(self._entries),
        }


__all__ = ["DictValueEditor", "DictEditDialog"]


