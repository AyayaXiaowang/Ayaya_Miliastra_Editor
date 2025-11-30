from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore, QtWidgets, QtGui

from ui.foundation.theme_manager import Colors


class UIWidgetPreviewItem(QtWidgets.QGraphicsItem):
    """UI控件预览图形项。

    该类由 `UIPreviewCanvas` 使用，用于在 QGraphicsScene 中展示和交互单个控件的预览：
    - 绘制控件外观与名称
    - 处理选中、高亮与调整手柄
    - 支持拖拽移动与八方向缩放
    """

    def __init__(self, config: dict, canvas: "UIPreviewCanvas", parent=None):
        super().__init__(parent)

        self.config = config
        self.canvas = canvas
        self.is_selected = False
        self.is_dragging = False
        self.is_resizing = False
        self.resize_handle: Optional[str] = None  # 'tl', 'tr', 'bl', 'br', 'l', 'r', 't', 'b'

        # 设置标志：内置控件不可拖拽/缩放
        is_builtin = self.config.get("is_builtin", False)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not is_builtin)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        # 缓存边界
        self.setCacheMode(QtWidgets.QGraphicsItem.CacheMode.DeviceCoordinateCache)

    def boundingRect(self) -> QtCore.QRectF:  # type: ignore[override]
        """边界矩形"""
        width = self.config["size"][0]
        height = self.config["size"][1]
        margin = 5 if self.is_selected else 0
        return QtCore.QRectF(-margin, -margin, width + margin * 2, height + margin * 2)

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:  # type: ignore[override]
        """绘制控件预览"""
        width = self.config["size"][0]
        height = self.config["size"][1]
        widget_type = self.config["widget_type"]
        is_builtin = self.config.get("is_builtin", False)

        # 设置抗锯齿
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # 背景色
        if is_builtin:
            bg_color = QtGui.QColor("#3A5A7A")  # 固有控件：蓝色系
        else:
            bg_color = QtGui.QColor("#4A4A4A")  # 通用控件：灰色系

        # 边框色（选中时使用主题主色系）
        if self.is_selected:
            border_color = QtGui.QColor(Colors.PRIMARY)
            border_width = 2
        else:
            border_color = QtGui.QColor("#666666")
            border_width = 1

        # 绘制背景
        rect = QtCore.QRectF(0, 0, width, height)
        painter.setPen(QtGui.QPen(border_color, border_width))
        painter.setBrush(QtGui.QBrush(bg_color))
        painter.drawRoundedRect(rect, 4, 4)

        # 绘制控件类型图标和文本
        painter.setPen(QtGui.QColor("#FFFFFF"))
        font = painter.font()
        font.setPixelSize(min(14, int(height * 0.3)))
        painter.setFont(font)

        # 控件名称
        widget_name = self.config.get("widget_name", widget_type)
        text_rect = QtCore.QRectF(5, 5, width - 10, height - 10)
        painter.drawText(
            text_rect,
            QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.TextFlag.TextWordWrap,
            widget_name,
        )

        # 如果选中，绘制调整手柄
        if self.is_selected and not is_builtin:
            self._draw_resize_handles(painter, width, height)

    def _draw_resize_handles(self, painter: QtGui.QPainter, width: float, height: float) -> None:
        """绘制调整手柄"""
        handle_size = 8
        handle_color = QtGui.QColor(Colors.PRIMARY)

        # 8个调整手柄位置
        handles = [
            (0, 0),  # 左上
            (width, 0),  # 右上
            (0, height),  # 左下
            (width, height),  # 右下
            (0, height / 2),  # 左中
            (width, height / 2),  # 右中
            (width / 2, 0),  # 上中
            (width / 2, height),  # 下中
        ]

        painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 1))
        painter.setBrush(QtGui.QBrush(handle_color))

        for x, y in handles:
            handle_rect = QtCore.QRectF(
                x - handle_size / 2,
                y - handle_size / 2,
                handle_size,
                handle_size,
            )
            painter.drawRect(handle_rect)

    def update_config(self, config: dict) -> None:
        """更新配置"""
        self.config = config
        self.setPos(config["position"][0], config["position"][1])
        self.setZValue(config.get("layer_index", 0))
        self.update()

    def set_selected(self, selected: bool) -> None:
        """设置选中状态"""
        self.is_selected = selected
        self.update()

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:  # type: ignore[override]
        """鼠标按下"""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # 检查是否点击在调整手柄上
            if self.is_selected and not self.config.get("is_builtin", False):
                handle = self._get_resize_handle(event.pos())
                if handle:
                    self.is_resizing = True
                    self.resize_handle = handle
                    event.accept()
                    return

            # 检查是否按下 Ctrl 键（多选模式）
            multi_select = event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier

            # 选中控件
            self.canvas.select_widget(self.config["widget_id"], multi_select=bool(multi_select))
            # 内置控件不允许拖拽
            if not self.config.get("is_builtin", False):
                self.is_dragging = True

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:  # type: ignore[override]
        """鼠标移动"""
        if self.is_resizing:
            self._handle_resize(event.pos())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:  # type: ignore[override]
        """鼠标释放"""
        if self.is_dragging:
            # 发送位置改变信号
            pos = self.pos()
            snapped_x = self.canvas.snap_to_grid_value(pos.x())
            snapped_y = self.canvas.snap_to_grid_value(pos.y())
            self.setPos(snapped_x, snapped_y)
            self.canvas.widget_moved.emit(self.config["widget_id"], snapped_x, snapped_y)
            self.is_dragging = False

        if self.is_resizing:
            # 发送大小改变信号
            width = self.config["size"][0]
            height = self.config["size"][1]
            self.canvas.widget_resized.emit(self.config["widget_id"], width, height)
            self.is_resizing = False
            self.resize_handle = None

        super().mouseReleaseEvent(event)

    def _get_resize_handle(self, pos: QtCore.QPointF) -> Optional[str]:
        """获取调整手柄"""
        width = self.config["size"][0]
        height = self.config["size"][1]
        handle_size = 8
        threshold = handle_size

        x, y = pos.x(), pos.y()

        # 检查四个角
        if abs(x) < threshold and abs(y) < threshold:
            return "tl"  # 左上
        if abs(x - width) < threshold and abs(y) < threshold:
            return "tr"  # 右上
        if abs(x) < threshold and abs(y - height) < threshold:
            return "bl"  # 左下
        if abs(x - width) < threshold and abs(y - height) < threshold:
            return "br"  # 右下

        # 检查四条边
        if abs(x) < threshold and threshold < y < height - threshold:
            return "l"  # 左
        if abs(x - width) < threshold and threshold < y < height - threshold:
            return "r"  # 右
        if abs(y) < threshold and threshold < x < width - threshold:
            return "t"  # 上
        if abs(y - height) < threshold and threshold < x < width - threshold:
            return "b"  # 下

        return None

    def _handle_resize(self, pos: QtCore.QPointF) -> None:
        """处理调整大小"""
        if not self.resize_handle:
            return

        width = self.config["size"][0]
        height = self.config["size"][1]
        item_pos = self.pos()

        # 最小尺寸
        min_size = 20

        x, y = pos.x(), pos.y()

        # 根据不同的手柄调整大小
        if "l" in self.resize_handle:
            # 左侧调整
            new_width = width - x
            if new_width >= min_size:
                self.config["size"] = (new_width, self.config["size"][1])
                self.setPos(item_pos.x() + x, item_pos.y())

        if "r" in self.resize_handle:
            # 右侧调整
            new_width = x
            if new_width >= min_size:
                self.config["size"] = (new_width, self.config["size"][1])

        if "t" in self.resize_handle:
            # 顶部调整
            new_height = height - y
            if new_height >= min_size:
                self.config["size"] = (self.config["size"][0], new_height)
                self.setPos(item_pos.x(), item_pos.y() + y)

        if "b" in self.resize_handle:
            # 底部调整
            new_height = y
            if new_height >= min_size:
                self.config["size"] = (self.config["size"][0], new_height)

        # 更新边界和重绘
        self.prepareGeometryChange()
        self.update()

    def hoverMoveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:  # type: ignore[override]
        """鼠标悬停移动"""
        if self.is_selected and not self.config.get("is_builtin", False):
            handle = self._get_resize_handle(event.pos())
            if handle:
                # 设置鼠标指针
                cursor_map: dict[str, QtCore.Qt.CursorShape] = {
                    "tl": QtCore.Qt.CursorShape.SizeFDiagCursor,
                    "tr": QtCore.Qt.CursorShape.SizeBDiagCursor,
                    "bl": QtCore.Qt.CursorShape.SizeBDiagCursor,
                    "br": QtCore.Qt.CursorShape.SizeFDiagCursor,
                    "l": QtCore.Qt.CursorShape.SizeHorCursor,
                    "r": QtCore.Qt.CursorShape.SizeHorCursor,
                    "t": QtCore.Qt.CursorShape.SizeVerCursor,
                    "b": QtCore.Qt.CursorShape.SizeVerCursor,
                }
                self.setCursor(cursor_map.get(handle, QtCore.Qt.CursorShape.ArrowCursor))
            else:
                self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

        super().hoverMoveEvent(event)


__all__ = ["UIWidgetPreviewItem"]


