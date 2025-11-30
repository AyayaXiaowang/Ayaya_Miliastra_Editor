"""Graphics preview scene and items for composite node virtual pins."""

from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.nodes.advanced_node_features import CompositeNodeConfig, VirtualPinConfig
from ui.foundation import input_dialogs
from ui.foundation.context_menu_builder import ContextMenuBuilder
from ui.foundation.theme_manager import Colors, Sizes, ThemeManager
from ui.foundation.view_utils import fit_view_to_scene_items
from ui.graph.library_mixins import ConfirmDialogMixin

PIN_SIZE = 12
PIN_SPACING = 40
NODE_PADDING = 25
MIN_NODE_WIDTH = 250
HEADER_HEIGHT = 45
CORNER_RADIUS = 12


class CompositeNodePreviewItem(QtWidgets.QGraphicsItem):
    """复合节点预览项，使用节点图相同的样式。"""

    def __init__(self, title: str, width: float, height: float):
        super().__init__()
        self.title = title
        self.width = width
        self.height = height
        self.title_font = QtGui.QFont("Microsoft YaHei", 11, QtGui.QFont.Weight.Bold)

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(-self.width / 2, -self.height / 2, self.width, self.height)

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.boundingRect()
        header_h = HEADER_HEIGHT

        title_path = QtGui.QPainterPath()
        title_path.moveTo(rect.left(), rect.top() + header_h)
        title_path.lineTo(rect.left(), rect.top() + CORNER_RADIUS)
        title_path.quadTo(rect.left(), rect.top(), rect.left() + CORNER_RADIUS, rect.top())
        title_path.lineTo(rect.right() - CORNER_RADIUS, rect.top())
        title_path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + CORNER_RADIUS)
        title_path.lineTo(rect.right(), rect.top() + header_h)
        title_path.closeSubpath()

        gradient = QtGui.QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.0, QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_START))
        gradient.setColorAt(1.0, QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_END))
        painter.fillPath(title_path, QtGui.QBrush(gradient))

        content_rect = QtCore.QRectF(rect.left(), rect.top() + header_h, rect.width(), rect.height() - header_h)
        content_color = QtGui.QColor("#1F1F1F")
        content_color.setAlpha(int(255 * 0.7))
        painter.setBrush(content_color)
        pen = QtGui.QPen(QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_END))
        pen.setWidth(2)
        painter.setPen(pen)

        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)
        painter.drawPath(path)

        painter.setFont(self.title_font)
        painter.setPen(QtGui.QColor("#FFFFFF"))
        title_rect = QtCore.QRectF(rect.left(), rect.top(), rect.width(), header_h)
        painter.drawText(
            title_rect.adjusted(12, 0, -12, 0),
            QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
            self.title,
        )


class VirtualPinItem(QtWidgets.QGraphicsItem):
    """虚拟引脚图形项，支持右键菜单与高亮。"""

    def __init__(self, pin_config: VirtualPinConfig, preview_widget: "CompositeNodePreviewGraphics"):
        super().__init__()
        self.pin_config = pin_config
        self.preview_widget = preview_widget
        self.number_text = "?"
        self.label_text = pin_config.pin_name
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.LeftButton | QtCore.Qt.MouseButton.RightButton)
        self._update_label_text()

    def _update_label_text(self) -> None:
        if not self.preview_widget or not self.preview_widget.composite_config:
            self.label_text = self.pin_config.pin_name
            return
        from engine.nodes.composite_node_manager import get_composite_node_manager

        manager = get_composite_node_manager()
        if not manager:
            return
        _, number = manager.get_pin_display_number(
            self.preview_widget.composite_config.composite_id, self.pin_config
        )
        self.number_text = str(number)
        self.label_text = self.pin_config.pin_name

    def boundingRect(self) -> QtCore.QRectF:
        port_radius = 6
        tag_width = 24
        tag_height = 20
        font_metrics = QtGui.QFontMetrics(QtGui.QFont("Microsoft YaHei", 9))
        text_width = font_metrics.horizontalAdvance(self.label_text)
        if self.pin_config.is_input:
            left = -tag_width - 8
            right = port_radius * 2 + 6 + text_width
        else:
            left = -text_width - port_radius * 2 - 6
            right = tag_width + 8
        return QtCore.QRectF(left, -tag_height / 2, right - left, tag_height)

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        port_radius = 6
        tag_width = 24
        tag_height = 20
        tag_radius = tag_height // 2
        if self.pin_config.is_input:
            tag_rect = QtCore.QRectF(-tag_width - 8, -tag_height / 2, tag_width, tag_height)
            gradient = QtGui.QLinearGradient(tag_rect.topLeft(), tag_rect.bottomLeft())
            gradient.setColorAt(0, QtGui.QColor("#FFD700"))
            gradient.setColorAt(1, QtGui.QColor("#FFA500"))
            painter.setBrush(gradient)
            painter.setPen(QtGui.QPen(QtGui.QColor("#CC8800"), 2))
            radius = 3 if self.pin_config.is_flow else tag_radius
            painter.drawRoundedRect(tag_rect, radius, radius)

            painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 1))
            painter.setFont(QtGui.QFont("Microsoft YaHei UI", 10, QtGui.QFont.Weight.Bold))
            painter.drawText(tag_rect, QtCore.Qt.AlignmentFlag.AlignCenter, self.number_text)

            if self.pin_config.is_flow:
                port_rect = QtCore.QRectF(0, -8, 20, 16)
                painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 2))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(port_rect, 4, 4)
                port_right = 20
            else:
                port_rect = QtCore.QRectF(0, -port_radius, port_radius * 2, port_radius * 2)
                painter.setPen(QtGui.QPen(QtGui.QColor("#D0D0D0"), 2))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawEllipse(port_rect)
                port_right = port_radius * 2

            painter.setFont(QtGui.QFont("Microsoft YaHei", 9))
            painter.setPen(QtGui.QColor("#E0E0E0"))
            painter.drawText(QtCore.QPointF(port_right + 6, 4), self.label_text)
        else:
            painter.setFont(QtGui.QFont("Microsoft YaHei", 9))
            painter.setPen(QtGui.QColor("#E0E0E0"))
            font_metrics = QtGui.QFontMetrics(QtGui.QFont("Microsoft YaHei", 9))
            text_width = font_metrics.horizontalAdvance(self.label_text)
            painter.drawText(QtCore.QPointF(-text_width - 6, 4), self.label_text)

            if self.pin_config.is_flow:
                port_rect = QtCore.QRectF(-20, -8, 20, 16)
                painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 2))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(port_rect, 4, 4)
                status_width = 20
            else:
                port_rect = QtCore.QRectF(-port_radius * 2, -port_radius, port_radius * 2, port_radius * 2)
                painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 2))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawEllipse(port_rect)
                status_width = port_radius * 2

            tag_rect = QtCore.QRectF(8, -tag_height / 2, tag_width, tag_height)
            gradient = QtGui.QLinearGradient(tag_rect.topLeft(), tag_rect.bottomLeft())
            gradient.setColorAt(0, QtGui.QColor("#FFD700"))
            gradient.setColorAt(1, QtGui.QColor("#FFA500"))
            painter.setBrush(gradient)
            painter.setPen(QtGui.QPen(QtGui.QColor("#CC8800"), 2))
            radius = 3 if self.pin_config.is_flow else tag_radius
            painter.drawRoundedRect(tag_rect, radius, radius)

            painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 1))
            painter.setFont(QtGui.QFont("Microsoft YaHei UI", 10, QtGui.QFont.Weight.Bold))
            painter.drawText(tag_rect, QtCore.Qt.AlignmentFlag.AlignCenter, self.number_text)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        builder = ContextMenuBuilder()
        builder.add_action("🔗 开启合并模式", self._start_merge_mode)
        builder.add_action("🗑️ 删除引脚", self._delete_pin)
        builder.exec_global(event.screenPos())

    def _start_merge_mode(self) -> None:
        if self.preview_widget:
            self.preview_widget.enter_merge_mode(self.pin_config)

    def _delete_pin(self) -> None:
        if self.preview_widget:
            self.preview_widget.delete_pin(self.pin_config)


class CompositeNodePreviewGraphics(QtWidgets.QGraphicsView, ConfirmDialogMixin):
    """复合节点预览图，负责展示虚拟引脚与网格背景。"""

    pin_deleted = QtCore.pyqtSignal(VirtualPinConfig)
    pins_merged = QtCore.pyqtSignal(list, str)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.composite_config: Optional[CompositeNodeConfig] = None
        self.pin_items: List[VirtualPinItem] = []
        self.merge_mode_active = False
        self.merge_base_pin: Optional[VirtualPinConfig] = None
        self.grid_size = 50

        self.scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.merge_toolbar = QtWidgets.QWidget(self)
        self.merge_toolbar.hide()
        self._setup_merge_toolbar()
        self.setStyleSheet(
            f"""
            QGraphicsView {{
                border: 1px solid {Colors.BORDER_LIGHT};
                border-radius: {Sizes.RADIUS_MEDIUM}px;
            }}
        """
        )

    def load_composite(self, composite: CompositeNodeConfig) -> None:
        self.composite_config = composite
        self._render_preview()

    def highlight_pin_names(self, pin_names: List[str]) -> None:
        if not pin_names:
            return
        names = set(pin_names)
        for pin_item in self.pin_items:
            pin_name = pin_item.pin_config.pin_name
            pin_item.setSelected(pin_name in names)
            pin_item.setOpacity(1.0 if pin_name in names else 0.3)
        self.scene.update()
        self.viewport().update()

    def clear_highlight(self) -> None:
        for pin_item in self.pin_items:
            pin_item.setSelected(False)
            pin_item.setOpacity(1.0)
        self.scene.update()
        self.viewport().update()

    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:  # noqa: N802
        ThemeManager.draw_grid_background(painter, rect, self.grid_size)

    def _setup_merge_toolbar(self) -> None:
        layout = QtWidgets.QHBoxLayout(self.merge_toolbar)
        layout.setContentsMargins(10, 5, 10, 5)
        self.merge_label = QtWidgets.QLabel("合并模式：选择要合并的引脚")
        self.merge_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-weight: bold;")
        layout.addWidget(self.merge_label)
        layout.addStretch()
        confirm_btn = QtWidgets.QPushButton("✓ 确定合并")
        confirm_btn.clicked.connect(self._confirm_merge)
        layout.addWidget(confirm_btn)
        cancel_btn = QtWidgets.QPushButton("✕ 取消")
        cancel_btn.clicked.connect(self._cancel_merge)
        layout.addWidget(cancel_btn)
        self.merge_toolbar.setStyleSheet(
            f"""
            QWidget {{
                background-color: {Colors.BG_SELECTED};
                border-radius: {Sizes.RADIUS_SMALL}px;
            }}
            {ThemeManager.button_style()}
        """
        )

    def _render_preview(self) -> None:
        self.scene.clear()
        self.pin_items.clear()
        if not self.composite_config:
            text_item = self.scene.addText("暂无复合节点\n\n右键内部节点的端口\n可暴露为虚拟引脚")
            text_item.setDefaultTextColor(QtGui.QColor("#888888"))
            text_item.setFont(QtGui.QFont("Microsoft YaHei UI", 12))
            text_item.setPos(-80, -40)
            return

        node_height = self._compute_height(self.composite_config.virtual_pins)
        node_width = MIN_NODE_WIDTH
        node_preview = CompositeNodePreviewItem(self.composite_config.node_name, node_width, node_height)
        node_preview.setPos(0, 0)
        node_preview.setZValue(0)
        self.scene.addItem(node_preview)

        self._create_pins(node_width, node_height, is_input=True)
        self._create_pins(node_width, node_height, is_input=False)

        items_rect = self.scene.itemsBoundingRect()
        self.scene.setSceneRect(items_rect.adjusted(-50, -30, 50, 30))
        self.scene.update()
        self.viewport().update()
        QtCore.QTimer.singleShot(50, lambda: fit_view_to_scene_items(self, self.scene))

    def _compute_height(self, pins: List[VirtualPinConfig]) -> float:
        input_flow = len([p for p in pins if p.is_input and p.is_flow])
        input_data = len([p for p in pins if p.is_input and not p.is_flow])
        output_flow = len([p for p in pins if not p.is_input and p.is_flow])
        output_data = len([p for p in pins if not p.is_input and not p.is_flow])
        max_pins = max(input_flow, input_data, output_flow, output_data, 1)
        return HEADER_HEIGHT + max_pins * PIN_SPACING + NODE_PADDING * 2

    def _create_pins(self, node_width: float, node_height: float, *, is_input: bool) -> None:
        if not self.composite_config:
            return
        y_start = -node_height / 2 + HEADER_HEIGHT + NODE_PADDING
        groups = [
            [
                p
                for p in self.composite_config.virtual_pins
                if p.is_input == is_input and p.is_flow
            ],
            [
                p
                for p in self.composite_config.virtual_pins
                if p.is_input == is_input and not p.is_flow
            ],
        ]
        for group in groups:
            group.sort(key=lambda p: p.pin_index)
            for pin in group:
                pin_item = VirtualPinItem(pin, self)
                pin_item.setZValue(10)
                x_pos = -node_width / 2 if is_input else node_width / 2
                pin_item.setPos(x_pos, y_start)
                self.scene.addItem(pin_item)
                self.pin_items.append(pin_item)
                y_start += PIN_SPACING

    def enter_merge_mode(self, base_pin: VirtualPinConfig) -> None:
        self.merge_mode_active = True
        self.merge_base_pin = base_pin
        self.merge_toolbar.show()
        self.merge_toolbar.setGeometry(0, 0, self.width(), 40)
        for pin_item in self.pin_items:
            pin = pin_item.pin_config
            if self._can_merge_with_base(pin):
                pin_item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                if pin == base_pin:
                    pin_item.setSelected(True)
            else:
                pin_item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                pin_item.setOpacity(0.3)

    def _can_merge_with_base(self, pin: VirtualPinConfig) -> bool:
        if not self.merge_base_pin:
            return False
        if pin.is_input != self.merge_base_pin.is_input:
            return False
        if pin.is_flow != self.merge_base_pin.is_flow:
            return False
        if pin.pin_type != self.merge_base_pin.pin_type:
            if pin.pin_type != "any" and self.merge_base_pin.pin_type != "any":
                return False
        return True

    def _confirm_merge(self) -> None:
        selected_pins = [pin_item.pin_config for pin_item in self.pin_items if pin_item.isSelected()]
        if len(selected_pins) < 2:
            self.show_warning("提示", "至少需要选择2个引脚进行合并")
            return
        merged_name = input_dialogs.prompt_text(
            self,
            "合并引脚",
            f"将 {len(selected_pins)} 个引脚合并为一个\n请输入合并后的引脚名称：",
            text=selected_pins[0].pin_name,
        )
        if merged_name:
            self.pins_merged.emit(selected_pins, merged_name)
        self._cancel_merge()

    def _cancel_merge(self) -> None:
        self.merge_mode_active = False
        self.merge_base_pin = None
        self.merge_toolbar.hide()
        for pin_item in self.pin_items:
            pin_item.setSelected(False)
            pin_item.setOpacity(1.0)
            pin_item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    def delete_pin(self, pin: VirtualPinConfig) -> None:
        if self.confirm("确认删除", f"确定要删除引脚 '{pin.pin_name}' 吗？"):
            self.pin_deleted.emit(pin)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.merge_toolbar.isVisible():
            self.merge_toolbar.setGeometry(0, 0, self.width(), 40)
        if self.scene.sceneRect().isValid():
            fit_view_to_scene_items(self, self.scene)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.scene.sceneRect().isValid():
            QtCore.QTimer.singleShot(50, lambda: fit_view_to_scene_items(self, self.scene))


