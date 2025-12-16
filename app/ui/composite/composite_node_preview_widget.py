"""Public widget that assembles the composite preview scene and pin list panel."""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from engine.nodes.advanced_node_features import CompositeNodeConfig, VirtualPinConfig
from app.ui.composite.composite_node_preview_controller import CompositeNodePreviewController
from app.ui.composite.pin_list_panel import PinListPanel
from app.ui.composite.preview_scene import CompositeNodePreviewGraphics
from app.ui.foundation.theme_manager import Colors, ThemeManager
from app.ui.foundation import dialog_utils


class CompositeNodePreviewWidget(QtWidgets.QWidget):
    """复合节点预览组件，主职责为装配子组件与处理对话框。"""

    pin_updated = QtCore.pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.composite_widget = None
        self.preview_graphics = CompositeNodePreviewGraphics()
        self.pin_panel = PinListPanel()
        self._controller = CompositeNodePreviewController(self.preview_graphics, self.pin_panel, self)
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        self.preview_graphics.setMinimumHeight(250)
        self.preview_graphics.setMaximumHeight(350)
        layout.addWidget(self.preview_graphics)
        layout.addWidget(self.pin_panel)
        self.setStyleSheet(
            f"""
            CompositeNodePreviewWidget {{
                background-color: {Colors.BG_CARD};
            }}
            {ThemeManager.scrollbar_style()}
        """
        )

    def _connect_signals(self) -> None:
        self.pin_panel.pin_name_changed.connect(self._handle_pin_name_changed)
        self._controller.pin_updated.connect(self.pin_updated)
        self._controller.pins_merge_finished.connect(self._show_merge_success)

    def set_composite_widget(self, widget) -> None:
        self.composite_widget = widget
        self._controller.set_composite_widget(widget)

    def load_composite(self, composite: CompositeNodeConfig) -> None:
        self._controller.load_composite(composite)

    def highlight_pin_names(self, pin_names: list[str]) -> None:
        self.preview_graphics.highlight_pin_names(pin_names)

    def clear_highlight(self) -> None:
        self.preview_graphics.clear_highlight()

    def _handle_pin_name_changed(self, pin: VirtualPinConfig, new_name: str) -> None:
        success, error = self._controller.rename_pin(pin, new_name)
        if not success:
            dialog_utils.show_warning_dialog(
                self,
                "错误",
                error or "无法重命名引脚",
            )
            self.pin_panel.refresh()

    def _show_merge_success(self, count: int, merged_name: str) -> None:
        dialog_utils.show_info_dialog(
            self,
            "合并成功",
            f"已将 {count} 个引脚合并为 '{merged_name}'",
        )


