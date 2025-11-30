from typing import Optional, Tuple

from PyQt6 import QtWidgets

from engine.configs.components.ui_control_group_model import DEVICE_PRESETS
from ui.panels.ui_control_group_preview import UIPreviewSection

__all__ = ["UIControlPanelBase"]


class UIControlPanelBase(QtWidgets.QWidget):
    """界面控件组面板的公共基类，封装左侧列表与预览区域的骨架。"""

    LEFT_PANEL_WIDTH = 280

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.preview_section = UIPreviewSection(DEVICE_PRESETS, self)
        self.preview_canvas = self.preview_section.preview_canvas

        self.preview_section.device_changed.connect(self._handle_device_changed)
        self.preview_canvas.widget_moved.connect(self._handle_widget_moved)
        self.preview_canvas.widget_resized.connect(self._handle_widget_resized)

    def create_left_container(self) -> Tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
        """创建左侧固定宽度的容器与布局。"""
        container = QtWidgets.QWidget()
        container.setFixedWidth(self.LEFT_PANEL_WIDTH)

        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)

        return container, layout

    def build_main_layout(self, left_widget: QtWidgets.QWidget) -> QtWidgets.QVBoxLayout:
        """构造左右分栏布局，并返回中部布局以便子类继续追加控件。"""
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(left_widget)

        middle_widget = QtWidgets.QWidget()
        middle_layout = QtWidgets.QVBoxLayout(middle_widget)
        middle_layout.setContentsMargins(5, 5, 5, 5)
        middle_layout.addWidget(self.preview_section, 1)

        main_layout.addWidget(middle_widget, 1)
        return middle_layout

    def _handle_device_changed(self, preset) -> None:
        """内部回调：根据设备预设更新画布，并触发可覆盖钩子。"""
        if preset is not None and hasattr(preset, "width") and hasattr(preset, "height"):
            self.preview_canvas.set_device(preset.width, preset.height)
        self._on_device_changed(preset)

    def _handle_widget_moved(self, widget_id: str, x: float, y: float) -> None:
        self._on_widget_moved(widget_id, x, y)

    def _handle_widget_resized(self, widget_id: str, width: float, height: float) -> None:
        self._on_widget_resized(widget_id, width, height)

    def _on_device_changed(self, preset) -> None:
        """子类可覆盖的设备切换回调（默认无需额外行为）。"""

    def _on_widget_moved(self, widget_id: str, x: float, y: float) -> None:
        """子类可覆盖的控件移动回调。"""

    def _on_widget_resized(self, widget_id: str, width: float, height: float) -> None:
        """子类可覆盖的控件尺寸变化回调。"""


    