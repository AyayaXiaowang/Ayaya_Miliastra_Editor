"""Panel widget responsible for rendering pin cards grouped by direction/type."""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from engine.nodes.advanced_node_features import CompositeNodeConfig, VirtualPinConfig
from ui.composite.pin_card_widget import PinCardWidget
from ui.foundation.theme_manager import Colors, ThemeManager


class PinListPanel(QtWidgets.QWidget):
    """引脚列表面板，按方向/类型分组展示所有虚拟引脚。"""

    pin_name_changed = QtCore.pyqtSignal(VirtualPinConfig, str)
    pin_delete_requested = QtCore.pyqtSignal(VirtualPinConfig)
    pin_merge_requested = QtCore.pyqtSignal(VirtualPinConfig)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.composite_config: CompositeNodeConfig | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title_label = QtWidgets.QLabel("引脚列表")
        title_label.setStyleSheet("font-size: 12px; font-weight: bold; padding: 5px;")
        layout.addWidget(title_label)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(150)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        layout.addWidget(self.scroll_area)

        self.container = QtWidgets.QWidget()
        self.cards_layout = QtWidgets.QVBoxLayout(self.container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.scroll_area.setWidget(self.container)

        self._apply_styles()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            PinListPanel {{
                background-color: {Colors.BG_CARD};
            }}
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            {ThemeManager.scrollbar_style()}
        """
        )

    def set_composite_config(self, composite: CompositeNodeConfig | None) -> None:
        self.composite_config = composite
        self.refresh()

    def refresh(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.composite_config:
            self.cards_layout.addStretch()
            return

        groups = [
            ("输入流程", [p for p in self.composite_config.virtual_pins if p.is_input and p.is_flow]),
            ("输入数据", [p for p in self.composite_config.virtual_pins if p.is_input and not p.is_flow]),
            ("输出流程", [p for p in self.composite_config.virtual_pins if not p.is_input and p.is_flow]),
            ("输出数据", [p for p in self.composite_config.virtual_pins if not p.is_input and not p.is_flow]),
        ]

        for group_name, pins in groups:
            if not pins:
                continue
            group_label = QtWidgets.QLabel(f"▼ {group_name}")
            group_label.setStyleSheet(
                f"""
                QLabel {{
                    font-size: 11px;
                    font-weight: bold;
                    color: {Colors.TEXT_SECONDARY};
                    padding: 8px 4px 4px 4px;
                }}
            """
            )
            self.cards_layout.addWidget(group_label)

            pins.sort(key=lambda p: p.pin_index)
            for pin in pins:
                card = PinCardWidget(pin, self.composite_config.composite_id, self)
                card.name_changed.connect(self.pin_name_changed)
                card.delete_requested.connect(self.pin_delete_requested)
                card.merge_requested.connect(self.pin_merge_requested)
                self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()


