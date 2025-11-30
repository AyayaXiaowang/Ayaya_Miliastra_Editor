"""界面控件组预览容器 - 统一设备下拉与画布布局。"""

from typing import Iterable, Optional

from PyQt6 import QtCore, QtWidgets

from ui.foundation.ui_preview_canvas import UIPreviewCanvas


class UIPreviewSection(QtWidgets.QWidget):
    """封装设备选择与 UIPreviewCanvas 的复合组件。"""

    device_changed = QtCore.pyqtSignal(object)

    def __init__(self, device_presets: Iterable[object], parent=None):
        super().__init__(parent)
        self._device_presets = list(device_presets)

        self.preview_canvas = UIPreviewCanvas()
        self._init_layout()
        self._populate_presets()

    def _init_layout(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QtWidgets.QHBoxLayout()
        toolbar.addWidget(QtWidgets.QLabel("设备:"))

        self.device_combo = QtWidgets.QComboBox()
        self.device_combo.setMinimumWidth(200)
        self.device_combo.currentIndexChanged.connect(self._on_combo_changed)
        toolbar.addWidget(self.device_combo)
        toolbar.addStretch()

        layout.addLayout(toolbar)
        layout.addWidget(self.preview_canvas, 1)

    def _populate_presets(self) -> None:
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for preset in self._device_presets:
            self.device_combo.addItem(f"{getattr(preset, 'name', 'Preset')}", preset)
        self.device_combo.blockSignals(False)
        if self.device_combo.count() > 0:
            self.device_combo.setCurrentIndex(0)
            self._emit_device_changed()

    def set_device_presets(self, presets: Iterable[object]) -> None:
        """更新可选设备预设列表。"""
        self._device_presets = list(presets)
        self._populate_presets()

    def current_preset(self) -> Optional[object]:
        """返回当前选中的设备预设。"""
        index = self.device_combo.currentIndex()
        if index < 0:
            return None
        return self.device_combo.itemData(index)

    def _on_combo_changed(self, _: int) -> None:
        self._emit_device_changed()

    def _emit_device_changed(self) -> None:
        preset = self.current_preset()
        self.device_changed.emit(preset)

