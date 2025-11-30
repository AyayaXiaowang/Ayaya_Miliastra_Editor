"""节点图引用列表表格控件。

封装“类型 / 名称 / 所属存档 / 操作”四列表格，
并在用户双击行或点击“操作”列的“跳转”单元格时发射统一的引用激活信号。
"""

from __future__ import annotations

from typing import List, Tuple, Optional, Mapping

from PyQt6 import QtCore, QtWidgets

from ui.foundation.theme_manager import ThemeManager


class GraphReferencesTableWidget(QtWidgets.QWidget):
    """节点图引用列表表格控件。

    引用数据约定为四元组列表：
    (entity_type, entity_id, entity_name, package_id)
    """

    # (entity_type, entity_id, package_id)
    reference_activated = QtCore.pyqtSignal(str, str, str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._references: List[Tuple[str, str, str, str]] = []

        self._setup_ui()

    # --- 公共 API ---

    def clear(self) -> None:
        """清空引用列表。"""
        self._references = []
        self._table.setRowCount(0)

    def set_references(
        self,
        references: List[Tuple[str, str, str, str]],
        package_name_map: Optional[Mapping[str, str]] = None,
    ) -> None:
        """设置引用数据并刷新表格。

        Args:
            references: 引用列表 (entity_type, entity_id, entity_name, package_id)。
            package_name_map: 可选的存档名称映射表，key 为 package_id，
                value 为展示用的存档名称；缺失时回退为 package_id 本身。
        """
        self._references = list(references)
        self._table.setRowCount(len(self._references))

        for row_index, (entity_type, entity_id, entity_name, package_id) in enumerate(
            self._references
        ):
            type_text = {
                "template": "📦 元件",
                "instance": "🎯 实体",
                "level_entity": "🗺️ 关卡实体",
            }.get(entity_type, entity_type)

            type_item = QtWidgets.QTableWidgetItem(type_text)
            self._table.setItem(row_index, 0, type_item)

            name_item = QtWidgets.QTableWidgetItem(entity_name)
            self._table.setItem(row_index, 1, name_item)

            if package_name_map is not None and package_id in package_name_map:
                package_name = package_name_map[package_id]
            else:
                package_name = package_id
            package_item = QtWidgets.QTableWidgetItem(package_name)
            self._table.setItem(row_index, 2, package_item)

            operation_item = QtWidgets.QTableWidgetItem("跳转")
            operation_item.setTextAlignment(
                QtCore.Qt.AlignmentFlag.AlignCenter
            )
            self._table.setItem(row_index, 3, operation_item)

    # --- 内部实现 ---

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        info_label = QtWidgets.QLabel(
            "💡 以下列出了使用此节点图的所有元件和实例。\n"
            "双击条目或点击“操作”列可以跳转到对应的编辑界面。"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(ThemeManager.subtle_info_style())
        layout.addWidget(info_label)

        table = QtWidgets.QTableWidget(self)
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["类型", "名称", "所属存档", "操作"])
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        table.cellClicked.connect(self._on_cell_clicked)

        layout.addWidget(table)

        self._table = table

    def _on_cell_double_clicked(self, row_index: int, column_index: int) -> None:
        if row_index < 0:
            return
        self._emit_reference_for_row(row_index)

    def _on_cell_clicked(self, row_index: int, column_index: int) -> None:
        if row_index < 0:
            return
        if column_index == 3:
            self._emit_reference_for_row(row_index)

    def _emit_reference_for_row(self, row_index: int) -> None:
        if row_index < 0 or row_index >= len(self._references):
            return
        entity_type, entity_id, _, package_id = self._references[row_index]
        self.reference_activated.emit(entity_type, entity_id, package_id)


__all__ = ["GraphReferencesTableWidget"]


