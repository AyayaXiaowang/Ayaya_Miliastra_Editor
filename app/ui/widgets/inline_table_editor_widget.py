"""通用的“工具栏 + 表格”内联编辑组件。

用于右侧属性面板、管理页面或其它需要紧凑表格编辑的场景：
- 上方提供“添加 / 删除”按钮；
- 下方承载一个按列配置的 `QTableWidget`；
- 支持统一的行级右键菜单（例如“删除参数”“删除当前行”等）；
- 对外仅通过信号暴露“请求新增一行 / 删除指定行”，不直接绑定业务数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.dialogs.table_edit_helpers import (
    wrap_click_to_edit_line_edit_for_table_cell,
)
from app.ui.dialogs.value_editor_common_widgets import ClickToEditLineEdit
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager


@dataclass(frozen=True)
class InlineTableColumnSpec:
    """列配置：标题 + 宽度策略。

    - title: 列标题文本；
    - resize_mode: 列宽模式（自适应/可交互/拉伸等），默认为 Interactive；
    - initial_width: 可选的初始列宽，仅在 >0 时生效。
    """

    title: str
    resize_mode: QtWidgets.QHeaderView.ResizeMode = (
        QtWidgets.QHeaderView.ResizeMode.Interactive
    )
    initial_width: Optional[int] = None


class InlineTableEditorWidget(QtWidgets.QWidget):
    """通用的“工具栏 + 表格”内联编辑组件。

    本组件仅负责：
    - 构建顶部工具栏与底部表格；
    - 应用统一的表格样式与行高/调色板；
    - 在用户点击“添加”按钮或右键菜单/删除按钮时发射信号：
      - row_add_requested()
      - row_delete_requested(row_index: int)

    具体的“如何新增一行 / 如何删除一行 / 如何与业务数据结构同步”完全由外部回调处理。
    """

    # 用户点击“添加”按钮时发射（不包含行索引，由外部决定插入位置）
    row_add_requested = QtCore.pyqtSignal()
    # 用户请求删除行时发射（包含行索引用于外部精确删除）
    row_delete_requested = QtCore.pyqtSignal(int)

    def __init__(
        self,
        *,
        parent: Optional[QtWidgets.QWidget],
        columns: Sequence[InlineTableColumnSpec],
        add_button_text: str,
        delete_button_text: Optional[str] = None,
        delete_action_text: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self._columns = list(columns)
        self._delete_action_text = delete_action_text or ""

        self.add_button: QtWidgets.QPushButton
        self.delete_button: Optional[QtWidgets.QPushButton] = None
        self.table: QtWidgets.QTableWidget

        self._setup_ui(add_button_text, delete_button_text)

    # ------------------------------------------------------------------ 公共辅助方法：右键转发与标准单元格工厂

    def attach_context_menu_forwarding(self, widget: QtWidgets.QWidget) -> None:
        """为嵌入表格单元格的子控件接入统一的右键菜单转发逻辑。

        典型用法：在为某个单元格设置 QLineEdit/QComboBox/QSpinBox 时调用本方法，
        使其右键事件统一落到表格级右键菜单，而不是使用各自控件的默认菜单。
        """
        widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        widget.customContextMenuRequested.connect(self._on_cell_widget_context_menu)

    def create_click_to_edit_line_edit_cell(
        self,
        row_index: int,
        column_index: int,
        *,
        text: str = "",
        placeholder: Optional[str] = None,
        min_width: int = 80,
        on_edited: Optional[Callable[[], None]] = None,
    ) -> ClickToEditLineEdit:
        """在指定单元格创建标准的“点击才能编辑”文本输入控件。

        约定：
        - 默认使用 ClickToEditLineEdit，焦点策略为 ClickFocus，仅显式点击输入框本身才进入编辑；
        - 通过 wrap_click_to_edit_line_edit_for_table_cell 收窄可编辑区域，点击单元格背景仅改变选中行；
        - 文本修改默认通过 editingFinished 触发 on_edited 回调，避免在每个字符输入时就写回模型。
        """
        line_edit = ClickToEditLineEdit(self.table)
        line_edit.setText(text)
        if placeholder:
            line_edit.setPlaceholderText(placeholder)
        line_edit.setClearButtonEnabled(True)
        line_edit.setMinimumWidth(int(min_width))
        line_edit.setFixedHeight(Sizes.INPUT_HEIGHT)
        if on_edited is not None:
            line_edit.editingFinished.connect(on_edited)
        container = wrap_click_to_edit_line_edit_for_table_cell(
            self.table,
            line_edit,
        )
        self.attach_context_menu_forwarding(line_edit)
        self.attach_context_menu_forwarding(container)
        self.table.setCellWidget(row_index, column_index, container)
        return line_edit

    # ------------------------------------------------------------------ 内部实现

    def _setup_ui(
        self,
        add_button_text: str,
        delete_button_text: Optional[str],
    ) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_SMALL)

        # 顶部工具栏：添加 / 删除 按钮
        toolbar_layout = QtWidgets.QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(Sizes.SPACING_SMALL)

        self.add_button = QtWidgets.QPushButton(add_button_text, self)
        self.add_button.setMinimumHeight(Sizes.BUTTON_HEIGHT)
        self.add_button.clicked.connect(self._on_add_clicked)
        toolbar_layout.addWidget(self.add_button)

        if delete_button_text:
            self.delete_button = QtWidgets.QPushButton(delete_button_text, self)
            self.delete_button.setMinimumHeight(Sizes.BUTTON_HEIGHT)
            self.delete_button.clicked.connect(self._on_delete_clicked)
            toolbar_layout.addWidget(self.delete_button)

        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)

        # 表格本体
        self.table = QtWidgets.QTableWidget(self)
        self.table.setColumnCount(len(self._columns))
        self.table.setHorizontalHeaderLabels([spec.title for spec in self._columns])
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        # 统一采用“内嵌控件编辑”模式，不启用 QTableWidget 自带的临时编辑器。
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._configure_table_appearance()

        if self._delete_action_text:
            self.table.setContextMenuPolicy(
                QtCore.Qt.ContextMenuPolicy.CustomContextMenu
            )
            self.table.customContextMenuRequested.connect(self._on_table_context_menu)

        layout.addWidget(self.table)

    def _configure_table_appearance(self) -> None:
        """统一配置表格的行高 / 列宽策略 / 调色板与 padding。"""
        self.table.setAlternatingRowColors(True)

        vertical_header = self.table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
            vertical_header.setDefaultSectionSize(
                Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL
            )

        horizontal_header = self.table.horizontalHeader()
        if horizontal_header is not None:
            for index, spec in enumerate(self._columns):
                horizontal_header.setSectionResizeMode(index, spec.resize_mode)
                if spec.initial_width is not None and spec.initial_width > 0:
                    horizontal_header.resizeSection(index, spec.initial_width)

        palette = self.table.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Base,
            QtGui.QColor(Colors.BG_CARD),
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.AlternateBase,
            QtGui.QColor(Colors.BG_MAIN),
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.Text,
            QtGui.QColor(Colors.TEXT_PRIMARY),
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.Highlight,
            QtGui.QColor(Colors.BG_SELECTED),
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.HighlightedText,
            QtGui.QColor(Colors.TEXT_PRIMARY),
        )
        self.table.setPalette(palette)
        # 使用全局表格样式，保持与信号列表/两行字段表格一致
        self.table.setStyleSheet(ThemeManager.table_style())

    # ------------------------------------------------------------------ 事件处理

    def _on_add_clicked(self) -> None:
        self.row_add_requested.emit()

    def _on_delete_clicked(self) -> None:
        row_index = self.table.currentRow()
        if row_index < 0:
            return
        self.row_delete_requested.emit(row_index)

    def _on_table_context_menu(self, pos: QtCore.QPoint) -> None:
        if not self._delete_action_text:
            return

        index = self.table.indexAt(pos)
        row_index = index.row()
        if row_index < 0:
            return

        self.table.setCurrentCell(row_index, index.column())

        def delete_current_row() -> None:
            self.row_delete_requested.emit(row_index)

        builder = ContextMenuBuilder(self.table)
        builder.add_action(self._delete_action_text, delete_current_row)

        viewport = self.table.viewport()
        if viewport is None:
            return
        builder.exec_for(viewport, pos)

    def _on_cell_widget_context_menu(self, pos: QtCore.QPoint) -> None:
        """将单元格内控件的右键事件转发给表格级右键菜单。"""
        sender_widget = self.sender()
        if not isinstance(sender_widget, QtWidgets.QWidget):
            return

        global_pos = sender_widget.mapToGlobal(pos)
        viewport_pos = self.table.viewport().mapFromGlobal(global_pos)
        self._on_table_context_menu(viewport_pos)


__all__ = ["InlineTableColumnSpec", "InlineTableEditorWidget"]


