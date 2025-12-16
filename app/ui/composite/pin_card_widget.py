"""Pin card widget for displaying and editing virtual pin metadata."""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets, QtGui

from engine.nodes.advanced_node_features import VirtualPinConfig
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager


class PinCardWidget(QtWidgets.QWidget):
    """虚拟引脚卡片组件，负责编号、类型与名称编辑。"""

    name_changed = QtCore.pyqtSignal(VirtualPinConfig, str)
    delete_requested = QtCore.pyqtSignal(VirtualPinConfig)
    merge_requested = QtCore.pyqtSignal(VirtualPinConfig)

    def __init__(self, pin_config: VirtualPinConfig, composite_id: str, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.pin_config = pin_config
        self.composite_id = composite_id
        self.name_edit: QtWidgets.QLineEdit | None = None
        self.name_label: QtWidgets.QLabel | None = None
        self.is_editing = False
        self._event_filter_target: QtWidgets.QWidget | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        number = self._resolve_pin_number()

        number_label = QtWidgets.QLabel(str(number))
        number_label.setFixedSize(28, 28)
        number_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        number_label.setStyleSheet(self._number_label_style())
        layout.addWidget(number_label)

        type_icon = "▭" if self.pin_config.is_flow else "●"
        type_label = QtWidgets.QLabel(type_icon)
        type_label.setStyleSheet(f"font-size: 16px; color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(type_label)

        self.name_label = QtWidgets.QLabel(self.pin_config.pin_name)
        self.name_label.setStyleSheet(f"font-size: 13px; color: {Colors.TEXT_PRIMARY}; font-weight: bold;")
        self.name_label.mouseDoubleClickEvent = self._start_edit  # type: ignore[assignment]
        layout.addWidget(self.name_label)

        layout.addStretch()

        mapping_label = QtWidgets.QLabel(f"映射: {len(self.pin_config.mapped_ports)}")
        mapping_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(mapping_label)

        type_tag = QtWidgets.QLabel(self.pin_config.pin_type)
        type_tag.setStyleSheet(
            f"""
            QLabel {{
                background-color: {Colors.BG_HEADER};
                color: {Colors.TEXT_SECONDARY};
                padding: 2px 8px;
                border-radius: 10px;
                font-size: 10px;
            }}
        """
        )
        layout.addWidget(type_tag)

        self.setStyleSheet(
            f"""
            PinCardWidget {{
                background-color: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER_LIGHT};
                border-radius: {Sizes.RADIUS_MEDIUM}px;
            }}
            PinCardWidget:hover {{
                border-color: {Colors.PRIMARY};
                background-color: {Colors.BG_CARD_HOVER};
            }}
        """
        )

        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _resolve_pin_number(self) -> str:
        from engine.nodes.composite_node_manager import get_composite_node_manager

        manager = get_composite_node_manager()
        if not manager:
            return "?"
        _, number = manager.get_pin_display_number(self.composite_id, self.pin_config)
        return str(number)

    def _number_label_style(self) -> str:
        radius = "3px" if self.pin_config.is_flow else "14px"
        return f"""
            QLabel {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {Colors.ACCENT_LIGHT},
                    stop:1 {Colors.ACCENT}
                );
                color: {Colors.TEXT_ON_PRIMARY};
                font-weight: bold;
                font-size: 11px;
                border: 2px solid {Colors.ACCENT};
                border-radius: {radius};
            }}
        """

    def _start_edit(self, event) -> None:  # type: ignore[override]
        if self.is_editing:
            return
        self.is_editing = True
        self.name_edit = QtWidgets.QLineEdit(self.pin_config.pin_name)
        self.name_edit.setStyleSheet(
            f"""
            QLineEdit {{
                font-size: 13px;
                color: {Colors.TEXT_PRIMARY};
                font-weight: bold;
                border: 1px solid {Colors.PRIMARY};
                background-color: {Colors.BG_INPUT};
                padding: 2px 4px;
            }}
        """
        )
        layout = self.layout()
        if self.name_label and layout:
            layout.replaceWidget(self.name_label, self.name_edit)
            self.name_label.hide()
        self.name_edit.selectAll()
        self.name_edit.setFocus()
        self.name_edit.editingFinished.connect(self._finish_edit)

        # 在卡片所在窗口级别安装事件过滤器，监听点击列表其它区域时自动结束编辑
        top_level = self.window()
        if isinstance(top_level, QtWidgets.QWidget):
            self._event_filter_target = top_level
            top_level.installEventFilter(self)

    def _finish_edit(self) -> None:
        if not self.is_editing or not self.name_edit or not self.name_label:
            return

        if self._event_filter_target is not None:
            self._event_filter_target.removeEventFilter(self)
            self._event_filter_target = None

        new_name = self.name_edit.text().strip()
        if new_name and new_name != self.pin_config.pin_name:
            self.name_changed.emit(self.pin_config, new_name)
            self.name_label.setText(new_name)
        layout = self.layout()
        if layout:
            layout.replaceWidget(self.name_edit, self.name_label)
        self.name_label.show()
        self.name_edit.deleteLater()
        self.name_edit = None
        self.is_editing = False

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        # 若当前处于编辑状态，且用户在窗口内任意位置点击了鼠标（不包含编辑框本身），则结束编辑
        if (
            self.is_editing
            and self.name_edit is not None
            and event.type() == QtCore.QEvent.Type.MouseButtonPress
        ):
            if isinstance(event, QtGui.QMouseEvent):
                global_pos = event.globalPosition().toPoint()
                local_pos = self.name_edit.mapFromGlobal(global_pos)
                if not self.name_edit.rect().contains(local_pos):
                    self._finish_edit()
        return super().eventFilter(watched, event)

    def _show_context_menu(self, pos: QtCore.QPoint) -> None:
        builder = ContextMenuBuilder(self)
        builder.add_action("🔗 开启合并模式", lambda: self.merge_requested.emit(self.pin_config))
        builder.add_action("🗑️ 删除引脚", lambda: self.delete_requested.emit(self.pin_config))
        builder.exec_for(self, pos)


