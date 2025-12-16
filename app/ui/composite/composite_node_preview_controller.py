"""Controller that coordinates preview scene, pin list, and composite manager IO."""

from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6 import QtCore

from engine.nodes.advanced_node_features import CompositeNodeConfig, VirtualPinConfig
from app.ui.composite.pin_list_panel import PinListPanel
from app.ui.composite.preview_scene import CompositeNodePreviewGraphics


class CompositeNodePreviewController(QtCore.QObject):
    """封装复合节点预览的状态更新与保存逻辑。"""

    pin_updated = QtCore.pyqtSignal()
    pins_merge_finished = QtCore.pyqtSignal(int, str)

    def __init__(
        self,
        preview_view: CompositeNodePreviewGraphics,
        pin_panel: PinListPanel,
        parent: Optional[QtCore.QObject] = None,
    ):
        super().__init__(parent)
        self.preview_view = preview_view
        self.pin_panel = pin_panel
        self.composite_widget = None
        self.composite_config: CompositeNodeConfig | None = None

        self.preview_view.pin_deleted.connect(self._handle_pin_deleted)
        self.preview_view.pins_merged.connect(self._handle_pins_merged)
        self.pin_panel.pin_delete_requested.connect(self.preview_view.delete_pin)
        self.pin_panel.pin_merge_requested.connect(self.preview_view.enter_merge_mode)

    def set_composite_widget(self, widget) -> None:
        self.composite_widget = widget

    def load_composite(self, composite: CompositeNodeConfig) -> None:
        self.composite_config = composite
        self.preview_view.load_composite(composite)
        self.pin_panel.set_composite_config(composite)

    def rename_pin(self, pin: VirtualPinConfig, new_name: str) -> Tuple[bool, Optional[str]]:
        if not self.composite_config:
            return False, "暂无复合节点"
        for existing in self.composite_config.virtual_pins:
            if existing is not pin and existing.pin_name == new_name:
                return False, f"引脚名称 '{new_name}' 已存在"
        pin.pin_name = new_name
        self._commit_changes(refresh_panel=False)
        return True, None

    def _handle_pin_deleted(self, pin: VirtualPinConfig) -> None:
        if not self.composite_config:
            return
        self.composite_config.virtual_pins = [p for p in self.composite_config.virtual_pins if p != pin]
        self._commit_changes(refresh_panel=True)

    def _handle_pins_merged(self, pins: List[VirtualPinConfig], merged_name: str) -> int:
        if not self.composite_config or len(pins) < 2:
            return 0
        target_pin = pins[0]
        target_pin.pin_name = merged_name
        for pin in pins[1:]:
            for mapped_port in pin.mapped_ports:
                exists = any(
                    mp.node_id == mapped_port.node_id and mp.port_name == mapped_port.port_name
                    for mp in target_pin.mapped_ports
                )
                if not exists:
                    target_pin.mapped_ports.append(mapped_port)
        self.composite_config.virtual_pins = [p for p in self.composite_config.virtual_pins if p not in pins[1:]]
        merged_count = len(pins)
        self._commit_changes(refresh_panel=True)
        self.pins_merge_finished.emit(merged_count, merged_name)
        return merged_count

    def _commit_changes(self, *, refresh_panel: bool) -> None:
        if self.composite_widget and self.composite_config:
            # 复合节点管理页面默认以逻辑只读方式工作：
            # - 允许在预览中合并/删除/重命名虚拟引脚
            # - 仅更新当前进程内的 CompositeNodeConfig，不写回函数文件
            is_read_only = getattr(self.composite_widget, "composite_logic_read_only", False)
            if not is_read_only:
                self.composite_widget.manager.update_composite_node(
                    self.composite_config.composite_id,
                    self.composite_config,
                )
        if refresh_panel:
            self.pin_panel.refresh()
        if self.composite_config:
            self.preview_view.load_composite(self.composite_config)
        self.pin_updated.emit()


