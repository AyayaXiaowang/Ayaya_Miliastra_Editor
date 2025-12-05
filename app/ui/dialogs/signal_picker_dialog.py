"""信号选择对话框 - 为节点绑定信号时使用的轻量选择器。

与管理面板中的信号列表复用同一套 `SignalTableWidget`，但只负责“选择哪一个信号”，
不单独维护持久化逻辑；信号的增删改仍由 `SignalTableWidget` 写回当前存档。
"""

from __future__ import annotations

from typing import Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.graph.models.package_model import SignalConfig
from ui.foundation.base_widgets import BaseDialog
from ui.foundation import dialog_utils
from ui.foundation.theme_manager import ThemeManager
from ui.widgets.signal_table_widget import SignalTableWidget


class SignalPickerDialog(BaseDialog):
    """信号选择对话框。

    输入为当前存档的 `{signal_id: SignalConfig}` 字典，输出为用户最终选中的 `signal_id`。
    """

    def __init__(
        self,
        signals: Dict[str, SignalConfig],
        parent: Optional[QtWidgets.QWidget] = None,
        current_signal_id: str = "",
    ) -> None:
        self._signals = signals
        self._selected_signal_id: str = str(current_signal_id or "")
        
        super().__init__(
            title="选择信号",
            width=720,
            height=520,
            parent=parent,
        )

        layout = self.content_layout

        info_label = QtWidgets.QLabel(
            "请选择要绑定的信号。当前版本中信号定义以代码资源为准，"
            "下方列表仅用于浏览与选择，不再作为修改信号定义的主入口。"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(ThemeManager.subtle_info_style())
        layout.addWidget(info_label)

        # 在选择对话框中仅作为“浏览 + 选择”视图使用，禁用内置对话框编辑，
        # 避免与代码级信号定义的实际维护入口产生语义冲突。
        self.table_widget = SignalTableWidget(self, use_dialog_editor=False)
        self.table_widget.set_signal_dict(self._signals)
        layout.addWidget(self.table_widget, 1)

        # 双击行 = 立即选择并关闭
        self.table_widget.table.itemDoubleClicked.connect(self._on_item_double_clicked)

        # 恢复已有绑定的预选中行
        if current_signal_id:
            self._restore_selection(current_signal_id)

    def _restore_selection(self, signal_id: str) -> None:
        """根据已有 signal_id 在表格中预选对应行。"""
        if not signal_id:
            return
        # 复用表格自身的查找逻辑
        row_index = self.table_widget._find_row_by_signal_id(signal_id)
        if row_index is None:
            return
        self.table_widget.table.setCurrentCell(row_index, 0)

    def _current_selected_signal_id(self) -> str:
        """读取当前表格选中的信号 ID（若无选中则返回空字符串）。"""
        row_index = self.table_widget.table.currentRow()
        if row_index < 0:
            return ""
        # 信号 ID 存放在隐藏列（索引 4）的 UserRole 和显示文本中
        id_item = self.table_widget.table.item(row_index, 4)
        if id_item is None:
            return ""
        return id_item.text() or ""

    def _on_item_double_clicked(self, _item: QtWidgets.QTableWidgetItem) -> None:
        """双击行时立即确认选择。"""
        selected_id = self._current_selected_signal_id()
        if not selected_id:
            return
        self._selected_signal_id = selected_id
        self.accept()

    def _on_accept(self) -> None:
        """点击确定按钮时读取当前选中行。"""
        selected_id = self._current_selected_signal_id()
        self._selected_signal_id = selected_id

    def validate(self) -> bool:
        """接受前同步当前选中的 signal_id。"""
        self._on_accept()
        return True

    def get_selected_signal_id(self) -> str:
        """返回用户最终选中的 signal_id（可能为空字符串表示未选择或放弃修改）。"""
        return self._selected_signal_id


__all__ = ["SignalPickerDialog"]


