"""信号列表组件 - 统一信号 CRUD 与搜索行为"""

from __future__ import annotations

from typing import Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.graph.models.package_model import SignalConfig
from app.ui.dialogs.signal_edit_dialog import SignalEditDialog
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager
from app.ui.foundation.dialog_utils import ask_yes_no_dialog, show_warning_dialog
from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.widgets.base_table_manager import BaseCrudTableWidget


class SignalTableWidget(BaseCrudTableWidget):
    """封装信号列表的工具栏、表格与 CRUD 逻辑。"""

    signals_modified = QtCore.pyqtSignal()
    # 外部编辑模式下的交互信号：由上层页面决定如何创建/编辑信号
    current_signal_changed = QtCore.pyqtSignal(str)
    request_add_signal = QtCore.pyqtSignal()
    request_edit_signal = QtCore.pyqtSignal(str)

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        *,
        use_dialog_editor: bool = True,
    ) -> None:
        super().__init__(parent)
        self._signal_dict: Optional[dict[str, SignalConfig]] = None
        # usage_stats: {signal_id: {"graph_count": int, "node_count": int}}
        self._usage_stats: Dict[str, Dict[str, int]] = {}
        # 在管理面板中可以关闭对话框编辑，改为外部详情面板编辑
        self._use_dialog_editor = use_dialog_editor

        self._setup_ui()
        self._update_enabled_state()

    def set_signal_dict(self, signal_dict: Optional[dict[str, SignalConfig]]) -> None:
        """绑定信号数据源（引用传入的 dict）。"""
        self._signal_dict = signal_dict
        self._refresh_table()
        self._update_enabled_state()

    def set_signal_usage_stats(self, usage_stats: Optional[Dict[str, Dict[str, int]]]) -> None:
        """设置信号使用统计信息，用于在表格中展示“使用情况”列。

        usage_stats 结构示例::

            {
                "signal_xxx": {"graph_count": 2, "node_count": 5},
                ...
            }
        """
        self._usage_stats = dict(usage_stats or {})
        # 使用统计只影响展示，不改变数据源；轻量刷新整表
        self._refresh_table()

    # --- 内部初始化 ---
    def _setup_ui(self) -> None:
        self.build_toolbar(
            [
                ("+ 新建信号", "add", self._add_signal),
                ("✏️ 编辑", "edit", self._edit_signal),
                ("🗑️ 删除", "delete", self._delete_signal),
            ],
            "搜索信号...",
            self._filter_signals,
        )
        self.table = QtWidgets.QTableWidget(self)
        # 列顺序：0=信号名, 1=参数数量, 2=描述, 3=使用情况, 4=信号ID(隐藏)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["信号名", "参数数量", "描述", "使用情况", "信号ID"]
        )
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setDefaultAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        # 统一信号列表表格的视觉风格：行高、交替行配色等
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(
            Sizes.INPUT_HEIGHT + Sizes.PADDING_SMALL
        )

        palette = self.table.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(Colors.BG_CARD))
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

        # 让信号管理页在管理面板/弹窗中都继承统一的表格 QSS 风格
        self.table.setStyleSheet(ThemeManager.table_style())

        self.main_layout.addWidget(self.table)

        if self._use_dialog_editor:
            self.table.itemDoubleClicked.connect(self._edit_signal)
        else:
            self.table.itemDoubleClicked.connect(self._on_item_double_clicked)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)

    # --- 状态控制 ---
    def _update_enabled_state(self) -> None:
        enabled = self._signal_dict is not None
        self.set_controls_enabled(enabled, (self.table,))
        if not enabled:
            self.table.setRowCount(0)

    def _refresh_table(self) -> None:
        self.table.setRowCount(0)
        if not self._signal_dict:
            return

        for signal_id, signal_config in self._signal_dict.items():
            self._append_signal_row(signal_id, signal_config)

        # 隐藏信号ID列（始终作为内部数据列存在）
        self.table.setColumnHidden(4, True)

        if self._use_dialog_editor:
            # 对话框/管理器中仍以多列表格形式展示
            self.table.setColumnHidden(1, False)
            self.table.setColumnHidden(2, False)
            self.table.setColumnHidden(3, False)
            self.table.setColumnWidth(0, 200)
            self.table.setColumnWidth(1, 100)
        else:
            # 管理面板中以“文件列表”形式展示：仅保留名称列可见
            self.table.setColumnHidden(1, True)
            self.table.setColumnHidden(2, True)
            self.table.setColumnHidden(3, True)
            self.table.resizeColumnToContents(0)

        if self.search_edit:
            self._filter_signals(self.search_edit.text())

    # --- 行为 ---
    def _add_signal(self) -> None:
        signal_dict = self._ensure_signal_dict()
        if signal_dict is None:
            return

        if not self._use_dialog_editor:
            # 外部编辑模式下仅发出请求，由上层页面负责在详情面板中创建新信号
            self.request_add_signal.emit()
            return

        dialog = SignalEditDialog(None, self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        signal_config = dialog.get_signal_config()
        if not signal_config:
            return

        if self._has_duplicate_name(signal_config.signal_name):
            show_warning_dialog(
                self,
                "警告",
                f"信号名 '{signal_config.signal_name}' 已存在，请使用不同的名称。",
            )
            return

        signal_id = self._generate_signal_id()
        signal_config.signal_id = signal_id
        signal_dict[signal_id] = signal_config
        self._append_signal_row(signal_id, signal_config)
        if self.search_edit:
            self._filter_signals(self.search_edit.text())
        self.signals_modified.emit()

    def _edit_signal(self) -> None:
        signal_dict = self._ensure_signal_dict()
        if signal_dict is None:
            return

        signal_id = self._get_selected_signal_id()
        if not signal_id:
            show_warning_dialog(self, "警告", "请先选择要编辑的信号")
            return

        if not self._use_dialog_editor:
            # 外部编辑模式下交给上层管理页面处理
            self.request_edit_signal.emit(signal_id)
            return

        signal_config = signal_dict.get(signal_id)
        if not signal_config:
            return

        dialog = SignalEditDialog(signal_config, self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        updated_config = dialog.get_signal_config()
        if not updated_config:
            return

        if self._has_duplicate_name(updated_config.signal_name, exclude_id=signal_id):
            show_warning_dialog(
                self,
                "警告",
                f"信号名 '{updated_config.signal_name}' 已被其他信号使用，请使用不同的名称。",
            )
            return

        updated_config.signal_id = signal_id
        signal_dict[signal_id] = updated_config
        row_index = self._find_row_by_signal_id(signal_id)
        if row_index is not None:
            self._populate_row(row_index, signal_id, updated_config)
        if self.search_edit:
            self._filter_signals(self.search_edit.text())
        self.signals_modified.emit()

    def _delete_signal(self) -> None:
        signal_dict = self._ensure_signal_dict()
        if signal_dict is None:
            return

        signal_id = self._get_selected_signal_id()
        if not signal_id:
            show_warning_dialog(self, "警告", "请先选择要删除的信号")
            return

        signal_config = signal_dict.get(signal_id)
        if not signal_config:
            return

        if not ask_yes_no_dialog(
            self,
            "确认删除",
            f"确定要删除信号 '{signal_config.signal_name}' 吗？\n"
            "删除后，使用此信号的节点将无法正常工作。",
        ):
            return

        del signal_dict[signal_id]
        row_index = self._find_row_by_signal_id(signal_id)
        if row_index is not None:
            self.table.removeRow(row_index)
        if self.search_edit:
            self._filter_signals(self.search_edit.text())
        self.signals_modified.emit()
        ToastNotification.show_message(self, f"已删除信号 '{signal_config.signal_name}'。", "success")

    # --- 工具方法 ---
    def _ensure_signal_dict(self) -> Optional[dict[str, SignalConfig]]:
        if self._signal_dict is None:
            show_warning_dialog(self, "警告", "当前未绑定信号数据源")
            return None
        return self._signal_dict

    def _get_selected_signal_id(self) -> Optional[str]:
        row_index = self.table.currentRow()
        if row_index < 0:
            return None
        item = self.table.item(row_index, 4)
        return item.text() if item else None

    def _has_duplicate_name(self, name: str, exclude_id: Optional[str] = None) -> bool:
        if not self._signal_dict:
            return False
        for signal_id, config in self._signal_dict.items():
            if exclude_id and signal_id == exclude_id:
                continue
            if config.signal_name == name:
                return True
        return False

    @staticmethod
    def _generate_signal_id() -> str:
        return generate_prefixed_id("signal")

    def _filter_signals(self, text: str) -> None:
        # 允许通过信号名 / 描述 / 信号ID 搜索；“使用情况”列不参与文本匹配
        self.filter_table_rows_by_columns(self.table, text, [0, 2, 4])

    def _append_signal_row(self, signal_id: str, signal_config: SignalConfig) -> int:
        row_index = self.table.rowCount()
        self.table.insertRow(row_index)
        self._populate_row(row_index, signal_id, signal_config)
        return row_index

    def _populate_row(
        self,
        row_index: int,
        signal_id: str,
        signal_config: SignalConfig,
    ) -> None:
        name_item = QtWidgets.QTableWidgetItem(signal_config.signal_name)
        name_item.setFont(
            QtGui.QFont("Microsoft YaHei UI", 10, QtGui.QFont.Weight.Bold)
        )
        self.table.setItem(row_index, 0, name_item)

        parameter_count = len(signal_config.parameters)
        param_item = QtWidgets.QTableWidgetItem(str(parameter_count))
        param_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_index, 1, param_item)

        desc_item = QtWidgets.QTableWidgetItem(signal_config.description or "无描述")
        desc_item.setForeground(QtGui.QColor(Colors.TEXT_SECONDARY))
        self.table.setItem(row_index, 2, desc_item)

        usage_entry = self._usage_stats.get(signal_id)
        if usage_entry:
            graph_count = int(usage_entry.get("graph_count", 0))
            node_count = int(usage_entry.get("node_count", 0))
            if graph_count > 0 or node_count > 0:
                usage_text = f"{graph_count} 图 / {node_count} 节点"
            else:
                usage_text = "未使用"
        else:
            usage_text = "未使用"
        usage_item = QtWidgets.QTableWidgetItem(usage_text)
        usage_item.setForeground(QtGui.QColor(Colors.PRIMARY_LIGHT))
        usage_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_index, 3, usage_item)

        id_item = QtWidgets.QTableWidgetItem(signal_id)
        id_item.setForeground(QtGui.QColor(Colors.TEXT_SECONDARY))
        id_item.setData(QtCore.Qt.ItemDataRole.UserRole, signal_id)
        self.table.setItem(row_index, 4, id_item)

    def _find_row_by_signal_id(self, signal_id: str) -> Optional[int]:
        for row_index in range(self.table.rowCount()):
            item = self.table.item(row_index, 4)
            if item and item.text() == signal_id:
                return row_index
        return None

    def select_signal(self, signal_id: str) -> None:
        """根据信号 ID 在表格中选中对应行。"""
        row_index = self._find_row_by_signal_id(signal_id)
        if row_index is None:
            return
        self.table.selectRow(row_index)

    def _on_item_double_clicked(self, _item: QtWidgets.QTableWidgetItem) -> None:
        """外部编辑模式下双击行时转发为编辑请求。"""
        signal_id = self._get_selected_signal_id()
        if not signal_id:
            return
        self.request_edit_signal.emit(signal_id)

    def _on_selection_changed(self) -> None:
        """选中行变化时通知上层页面更新详情预览。"""
        signal_id = self._get_selected_signal_id() or ""
        self.current_signal_changed.emit(signal_id)

