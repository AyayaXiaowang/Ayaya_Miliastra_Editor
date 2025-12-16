from __future__ import annotations

from typing import List, Optional, Sequence

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.dialogs.table_edit_helpers import (
    wrap_click_to_edit_line_edit_for_table_cell,
)
from app.ui.dialogs.value_editor_common_widgets import ClickToEditLineEdit
from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.theme_manager import Sizes, ThemeManager, Icons as ThemeIcons


class _ListTableEditorWidget(QtWidgets.QWidget):
    """封装“序号 + 值”两列表格及“添加/删除元素”工具栏的基础组件。

    - `ListValueEditor` 与 `ListEditDialog` 复用此组件，保证列宽策略、行高和占位文案一致。
    - 通过 `use_click_to_edit_line_edit` 控制是否使用 `ClickToEditLineEdit` + 包裹容器，
      以适配内联编辑（更窄的可编辑命中区域）和弹窗编辑（直接点击即可编辑）的不同交互需求。
    """

    values_changed = QtCore.pyqtSignal()

    def __init__(
        self,
        *,
        placeholder_text: str,
        use_click_to_edit_line_edit: bool,
        initial_values: Optional[Sequence[str]] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._placeholder_text = placeholder_text
        self._use_click_to_edit_line_edit = use_click_to_edit_line_edit
        self._values: List[str] = []
        self._is_read_only: bool = False

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(Sizes.SPACING_SMALL)

        toolbar_layout = QtWidgets.QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(Sizes.SPACING_SMALL)
        # 保留添加/删除按钮属性以兼容外部只读逻辑，但在交互上不再展示独立工具栏按钮，
        # 列表元素的新增通过“始终存在的最后一行占位行”完成，删除则通过右键菜单触发。
        self.add_button = QtWidgets.QPushButton("+ 添加元素", self)
        self.remove_button = QtWidgets.QPushButton("- 删除元素", self)
        self.add_button.setVisible(False)
        self.remove_button.setVisible(False)
        toolbar_layout.addStretch()
        root_layout.addLayout(toolbar_layout)

        self.table = QtWidgets.QTableWidget(self)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["序号", "值"])
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
        vertical_header = self.table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
            default_row_height = Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL
            vertical_header.setDefaultSectionSize(default_row_height)
        # 使用按像素滚动，避免当列表元素较多、单行高度较大时，滚轮滚动一步就跳过大段内容。
        self.table.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        root_layout.addWidget(self.table)

        self.add_button.clicked.connect(self._on_add_clicked)
        self.remove_button.clicked.connect(self._on_remove_clicked)

        # 行级右键菜单仅提供“删除当前行”，与结构体字段/字典子表格的交互保持一致。
        self.table.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)

        # 双击最后一行时无需特殊逻辑：最后一行本身即为空白占位行，用户直接在其中输入即可。

        if initial_values:
            for initial_value in initial_values:
                self._add_row(initial_value)
        if self.table.rowCount() == 0:
            self._add_row("")
        # 确保始终存在一个尾部空白占位行，用于追加新元素（只读模式下不会附加该占位行）。
        self._ensure_trailing_placeholder_row()
        self._sync_values_from_table()
        self._update_table_height()

    def set_values(self, values: Sequence[str]) -> None:
        self.table.setRowCount(0)
        self._values = []
        for value_text in values:
            self._add_row(value_text)
        if self.table.rowCount() == 0:
            self._add_row("")
        self._sync_values_from_table()
        self._update_table_height()
        self.values_changed.emit()

    def get_values(self) -> List[str]:
        self._sync_values_from_table()
        return list(self._values)

    def _create_value_editor_widget(self, value_text: str) -> QtWidgets.QWidget:
        if self._use_click_to_edit_line_edit:
            line_edit = ClickToEditLineEdit(value_text, self.table)
            line_edit.setPlaceholderText(self._placeholder_text)
            line_edit.setClearButtonEnabled(True)
            line_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
            line_edit.editingFinished.connect(self._on_value_edited)
            return wrap_click_to_edit_line_edit_for_table_cell(self.table, line_edit)

        line_edit = QtWidgets.QLineEdit(value_text, self.table)
        line_edit.setPlaceholderText(self._placeholder_text)
        line_edit.setClearButtonEnabled(True)
        line_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        line_edit.editingFinished.connect(self._on_value_edited)
        return line_edit

    def _add_row(self, value_text: str) -> None:
        row_index = self.table.rowCount()
        self.table.insertRow(row_index)

        index_item = QtWidgets.QTableWidgetItem(str(row_index + 1))
        index_item.setFlags(
            QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled
        )
        self.table.setItem(row_index, 0, index_item)

        editor_widget = self._create_value_editor_widget(value_text)
        self.table.setCellWidget(row_index, 1, editor_widget)
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

    def _sync_values_from_table(self) -> None:
        synchronized_values: List[str] = []
        row_count = self.table.rowCount()
        for row_index in range(row_count):
            cell_widget = self.table.cellWidget(row_index, 1)
            value_text = self._extract_text_from_cell_widget(cell_widget)
            synchronized_values.append(value_text)
        self._values = synchronized_values

    def _extract_text_from_cell_widget(
        self,
        cell_widget: Optional[QtWidgets.QWidget],
    ) -> str:
        if isinstance(cell_widget, QtWidgets.QLineEdit):
            return cell_widget.text()
        if isinstance(cell_widget, QtWidgets.QWidget):
            inner_edit = cell_widget.findChild(QtWidgets.QLineEdit)
            if isinstance(inner_edit, QtWidgets.QLineEdit):
                return inner_edit.text()
        return ""

    def _on_add_clicked(self) -> None:
        self._add_row("")
        self._refresh_indices()
        self._sync_values_from_table()
        self._ensure_trailing_placeholder_row()
        self.values_changed.emit()

    def _on_remove_clicked(self) -> None:
        current_row_index = self.table.currentRow()
        if current_row_index < 0:
            return
        self.table.removeRow(current_row_index)
        self._refresh_indices()
        self._sync_values_from_table()
        self._update_table_height()
        self.values_changed.emit()

    def _on_value_edited(self) -> None:
        self._sync_values_from_table()
        # 当用户在最后一行输入内容后，自动在表格末尾追加新的空白占位行，
        # 保证“最后一行始终为空白，用于新增元素”的体验。
        self._ensure_trailing_placeholder_row()
        self.values_changed.emit()

    def _update_table_height(self) -> None:
        """根据当前行数调整列表子表格高度，尽量让所有元素完整展示。"""
        header = self.table.horizontalHeader()
        vertical_header = self.table.verticalHeader()
        default_row_height = Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL

        # 根据单元格内容自动调整行高，避免当值单元格嵌套更复杂编辑器时出现裁剪。
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
        """确保表格末尾始终保留一行空白占位行，用于快速新增元素。"""
        if self._is_read_only:
            return
        row_count = self.table.rowCount()
        if row_count == 0:
            self._add_row("")
            return
        last_row_index = row_count - 1
        last_cell_widget = self.table.cellWidget(last_row_index, 1)
        last_text = self._extract_text_from_cell_widget(last_cell_widget)
        if last_text.strip():
            self._add_row("")

    def set_read_only(self, read_only: bool) -> None:
        """切换列表子表格的只读状态。

        只读模式下会移除尾部用于“新增”的空白占位行，避免在不可保存的视图中出现伪“新建”入口。
        """
        self._is_read_only = bool(read_only)
        if not self._is_read_only:
            # 非只读模式下保持原有行为，由上层控制是否允许保存。
            return

        row_count = self.table.rowCount()
        if row_count <= 0:
            return

        # 假定最后一行为“新增占位行”，直接移除即可，不影响已有元素。
        last_row_index = row_count - 1
        self.table.removeRow(last_row_index)
        self._refresh_indices()
        self._update_table_height()

    def _on_table_context_menu(self, pos: QtCore.QPoint) -> None:
        """右键菜单：删除当前行。

        新增元素通过始终存在的最后一行占位行完成，这里不再提供显式“新增”按钮。
        """
        index = self.table.indexAt(pos)
        row_index = index.row()
        if row_index < 0:
            return

        def delete_current_row() -> None:
            self.table.removeRow(row_index)
            self._refresh_indices()
            self._sync_values_from_table()
            self._ensure_trailing_placeholder_row()
            self._update_table_height()
            self.values_changed.emit()

        builder = ContextMenuBuilder(self.table)
        builder.add_action("删除当前行", delete_current_row)
        builder.exec_for(self.table.viewport(), pos)

    # 调试辅助：在列表展开时打印高度信息，便于校准父表格行高逻辑
    def debug_print_heights(self) -> None:
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
            "[UI调试/ListValueEditor]",
            f"元素个数={self.table.rowCount()}",
            f"header_height={header_height}",
            f"rows_height={rows_height}",
            f"total_height={total_height}",
            f"table.sizeHint={self.table.sizeHint()}",
        )


class ListValueEditor(QtWidgets.QWidget):
    """列表类型字段的“数据值”单元格：内联子表格编辑。

    在字段行内部直接展示列表元素子集，不再弹出额外对话框。
    元素本身没有名字，数据类型由父级字段的“数据类型”决定。
    """

    value_changed = QtCore.pyqtSignal()

    def __init__(
        self,
        element_type_name: str,
        values: Optional[Sequence[str]] = None,
        parent: Optional[QtWidgets.QWidget] = None,
        enable_collapse: bool = True,
    ) -> None:
        super().__init__(parent)
        self._element_type_name = element_type_name
        self._is_collapsed: bool = False
        self._header_detached: bool = False
        self._enable_collapse: bool = enable_collapse

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(Sizes.SPACING_SMALL)
        self._root_layout = root_layout

        # 顶部：折叠按钮 + 摘要（例如“3 个元素”），字段很多时可以先折叠列表值。
        self._header_container = QtWidgets.QWidget(self)
        header_layout = QtWidgets.QHBoxLayout(self._header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(Sizes.SPACING_SMALL)

        self.collapse_button = QtWidgets.QToolButton(self)
        self.collapse_button.setCheckable(True)
        self.collapse_button.setChecked(False)
        # 使用统一的 Chevron 文本图标，避免平台默认箭头风格不一致。
        self.collapse_button.setText(ThemeIcons.CHEVRON_DOWN)
        self.collapse_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        if self._enable_collapse:
            self.collapse_button.clicked.connect(self._on_toggle_collapsed)
        else:
            # 在禁用折叠模式下隐藏按钮，仅保留摘要文本
            self.collapse_button.setVisible(False)

        self.summary_label = QtWidgets.QLabel(self)
        # 计数信息采用更轻量的提示样式，减少在字段编辑区的视觉干扰。
        self.summary_label.setStyleSheet(ThemeManager.subtle_info_style())

        header_layout.addWidget(self.collapse_button)
        header_layout.addWidget(self.summary_label)
        header_layout.addStretch()
        root_layout.addWidget(self._header_container)

        initial_values: List[str] = list(values) if values else []
        self._table_editor = _ListTableEditorWidget(
            placeholder_text="元素值",
            use_click_to_edit_line_edit=True,
            initial_values=initial_values,
            parent=self,
        )
        root_layout.addWidget(self._table_editor)

        # 暴露底层表格与按钮，方便上层在极少数情况下直接自定义行为。
        self.table = self._table_editor.table
        self.add_button = self._table_editor.add_button
        self.remove_button = self._table_editor.remove_button

        self._table_editor.values_changed.connect(self._on_values_changed)

        self.setMinimumHeight((Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL) * 2)
        self._update_summary_text()

        # 默认折叠列表详情，先展示紧凑的“折叠 + 摘要”视图，避免大数据量时初始展开造成卡顿；
        # 当显式禁用折叠功能时，保持子表格常显。
        if self._enable_collapse:
            self._on_toggle_collapsed()
        else:
            self._is_collapsed = False
            self._table_editor.setVisible(True)

    def set_read_only(self, read_only: bool) -> None:
        """切换列表值编辑器的只读状态。

        当前只在结构体/变量等上层视图处于“不可保存”模式时使用，用于隐藏末尾的“新增占位行”，
        避免给用户造成可以新增元素的错觉；实际字段写回逻辑仍由上层控制。
        """
        self._table_editor.set_read_only(read_only)

    def create_header_proxy(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """将折叠按钮与摘要行从内部布局中抽离，嵌入外层表格的主行中。

        默认情况下，ListValueEditor 自己持有顶部“折叠 + X 个元素”那一行。
        当结构体编辑器希望在字段主行展示这部分信息时，会调用本方法：
        - 从自身垂直布局中移除头部容器
        - 将其重新挂载到外部提供的 parent 上
        - 内部仅保留子表格与“添加/删除元素”工具栏作为详情行内容
        """
        if self._header_detached:
            return self._header_container
        self._header_detached = True

        layout = self.layout()
        if isinstance(layout, QtWidgets.QVBoxLayout):
            layout.removeWidget(self._header_container)

        self._header_container.setParent(parent)
        return self._header_container

    def _wrap_cell_line_edit(
        self,
        line_edit: QtWidgets.QLineEdit,
    ) -> QtWidgets.QWidget:
        """为子表格中的单行输入框提供容器包装，减小“可编辑命中区域”。

        这样点击单元格行背景只会选中整行，不会立刻把焦点交给内部编辑框，
        必须显式点击输入框本身才进入编辑态，与外层结构体表格保持一致。
        """
        return wrap_click_to_edit_line_edit_for_table_cell(self.table, line_edit)

    def _update_summary_text(self) -> None:
        element_count = len(self.get_values())
        if element_count == 0:
            summary_text = "空列表"
        elif element_count == 1:
            summary_text = "1 个元素"
        else:
            summary_text = f"{element_count} 个元素"
        self.summary_label.setText(summary_text)

    def _on_values_changed(self) -> None:
        self._update_summary_text()
        self.value_changed.emit()

    def _on_toggle_collapsed(self) -> None:
        if not self._enable_collapse:
            return
        self._is_collapsed = not self._is_collapsed
        is_visible = not self._is_collapsed
        # 折叠时仅隐藏子表格与工具栏，保留主行中的折叠控制与摘要。
        self._table_editor.setVisible(is_visible)
        self.collapse_button.setText(
            ThemeIcons.CHEVRON_RIGHT if self._is_collapsed else ThemeIcons.CHEVRON_DOWN
        )
        # 使用图标颜色区分折叠状态：收起时弱化箭头颜色，展开时恢复默认。
        if self._is_collapsed:
            collapsed_color = ThemeManager.Colors.TEXT_DISABLED
            self.collapse_button.setStyleSheet(
                f"QToolButton {{ color: {collapsed_color}; }}"
            )
        else:
            self.collapse_button.setStyleSheet("")
        # 通知父表格根据新的 sizeHint 重新调整行高。
        self.updateGeometry()
        self.value_changed.emit()

        # 仅在展开时打印一次调试信息，帮助检查高度计算是否合理
        if is_visible:
            self._table_editor._update_table_height()
            self._table_editor.debug_print_heights()

    def is_collapsed(self) -> bool:
        return self._is_collapsed

    def get_values(self) -> List[str]:
        return self._table_editor.get_values()
        
        
class ListEditDialog(BaseDialog):
    """编辑列表值的对话框。"""
    
    def __init__(
        self,
        *,
        element_type_name: str,
        initial_values: Sequence[str],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        self._element_type_name = element_type_name
        self._values: List[str] = list(initial_values)
        
        super().__init__(
            title=f"编辑列表（元素类型：{element_type_name}）",
            width=480,
            height=400,
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
        
        self._table_editor = _ListTableEditorWidget(
            placeholder_text="元素值",
            use_click_to_edit_line_edit=False,
            initial_values=self._values,
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
        self._values = self._table_editor.get_values()
        return True
    
    def get_values(self) -> List[str]:
        return list(self._values)


__all__ = ["ListValueEditor", "ListEditDialog"]


