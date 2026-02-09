from __future__ import annotations

from PyQt6 import QtWidgets


def wrap_click_to_edit_line_edit_for_table_cell(
    table_widget: QtWidgets.QTableWidget,
    line_edit: QtWidgets.QLineEdit,
) -> QtWidgets.QWidget:
    """为嵌入 QTableWidget 的 ClickToEditLineEdit 提供统一的容器包装。

    使用方式：
    - 将 QLineEdit 的 parent 设为目标表格（例如 params_table）
    - 调用本函数获取外层 QWidget 容器
    - 通过 table_widget.setCellWidget(row, column, container) 嵌入单元格

    容器内部使用垂直布局，保留少量底部留白并通过 addStretch(1)
    收窄“可编辑命中区域”，点击单元格行背景仅改变选中状态，
    必须显式点击输入框本身才进入编辑态。
    """
    return wrap_inline_editor_for_table_cell(table_widget, line_edit)


def wrap_inline_editor_for_table_cell(
    table_widget: QtWidgets.QTableWidget,
    editor_widget: QtWidgets.QWidget,
) -> QtWidgets.QWidget:
    """为嵌入 QTableWidget 的行内编辑控件提供统一的容器包装。

    设计目标：
    - 通过在控件下方追加 `addStretch(1)` 收窄“可编辑命中区域”；
    - 点击单元格行背景仅改变选中状态，必须显式点击控件本身才进入交互态；
    - 便于在不同表格中复用相同的“工具栏 + 表格”的交互习惯。

    注意：容器仅负责布局与命中区域控制；若需要在只读模式下铺满单元格背景，
    请由上层组件在切换只读状态时对容器本身设置背景样式。
    """
    container = QtWidgets.QWidget(table_widget)
    layout = QtWidgets.QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(editor_widget)
    layout.addStretch(1)
    return container


__all__ = [
    "wrap_click_to_edit_line_edit_for_table_cell",
    "wrap_inline_editor_for_table_cell",
]


