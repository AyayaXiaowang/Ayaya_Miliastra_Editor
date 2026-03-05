"""Panel widget responsible for rendering pin cards grouped by direction/type."""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from engine.nodes.advanced_node_features import CompositeNodeConfig, VirtualPinConfig
from app.ui.composite.pin_card_widget import PinCardWidget


class PinListPanel(QtWidgets.QWidget):
    """引脚列表面板，按方向/类型分组展示所有虚拟引脚。"""

    pin_name_changed = QtCore.pyqtSignal(VirtualPinConfig, str)
    pin_type_changed = QtCore.pyqtSignal(VirtualPinConfig, str)
    pin_delete_requested = QtCore.pyqtSignal(VirtualPinConfig)
    pin_merge_requested = QtCore.pyqtSignal(VirtualPinConfig)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        # 通过 objectName 让全局主题样式精确命中，避免在面板内拼接 QSS
        self.setObjectName("pinListPanel")
        self.composite_config: CompositeNodeConfig | None = None
        # 当前页面是否允许修改“引脚类型”（不可保存时应禁用，避免产生可改但无法落盘的错觉）
        self._type_editable: bool = True
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title_label = QtWidgets.QLabel("引脚列表")
        title_label.setObjectName("pinListTitle")
        layout.addWidget(title_label)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setObjectName("pinListScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(150)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        layout.addWidget(self.scroll_area)

        self.container = QtWidgets.QWidget()
        self.cards_layout = QtWidgets.QVBoxLayout(self.container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.scroll_area.setWidget(self.container)

    def set_composite_config(self, composite: CompositeNodeConfig | None) -> None:
        self.composite_config = composite
        self.refresh()

    def set_type_editable(self, editable: bool) -> None:
        """设置“引脚类型”是否允许修改（由上层按可保存状态控制）。"""
        new_value = bool(editable)
        if getattr(self, "_type_editable", True) == new_value:
            return
        self._type_editable = new_value
        # 仅当已加载复合节点时刷新；避免在初始化阶段重复清空/重建 UI。
        if self.composite_config is not None:
            self.refresh()

    def refresh(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.composite_config:
            self.cards_layout.addStretch()
            return

        # 顶部：当前复合节点标题（便于复制/复用命名）
        composite_name_text = str(
            getattr(self.composite_config, "node_name", "") or getattr(self.composite_config, "composite_id", "") or ""
        ).strip()
        if composite_name_text:
            header_row = QtWidgets.QWidget(self.container)
            header_layout = QtWidgets.QHBoxLayout(header_row)
            header_layout.setContentsMargins(6, 8, 6, 4)
            header_layout.setSpacing(8)

            prefix_label = QtWidgets.QLabel("复合节点：", header_row)
            prefix_label.setObjectName("pinListHeaderPrefix")
            header_layout.addWidget(prefix_label)

            name_label = QtWidgets.QLabel(composite_name_text, header_row)
            name_label.setObjectName("pinListHeaderName")
            name_label.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
                | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            name_label.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
            header_layout.addWidget(name_label, 1)

            copy_button = QtWidgets.QToolButton(header_row)
            copy_button.setObjectName("pinCopyButton")
            copy_button.setText("📋")
            copy_button.setToolTip("复制复合节点标题")
            copy_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            copy_button.setFixedSize(24, 24)
            copy_button.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(composite_name_text))
            header_layout.addWidget(copy_button)

            self.cards_layout.addWidget(header_row)

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
            group_label.setObjectName("pinListGroupLabel")
            self.cards_layout.addWidget(group_label)

            pins.sort(key=lambda p: p.pin_index)
            for pin in pins:
                card = PinCardWidget(
                    pin,
                    self.composite_config.composite_id,
                    self,
                    type_editable=bool(getattr(self, "_type_editable", True)),
                )
                card.name_changed.connect(self.pin_name_changed)
                card.type_changed.connect(self.pin_type_changed)
                card.delete_requested.connect(self.pin_delete_requested)
                card.merge_requested.connect(self.pin_merge_requested)
                self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()


