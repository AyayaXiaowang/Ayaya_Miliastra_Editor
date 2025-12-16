"""
UI预览画布 - 实时可视化界面控件
"""

from PyQt6 import QtCore, QtWidgets, QtGui
from typing import Dict, Optional

from app.ui.foundation.theme_manager import Colors, ThemeManager
from app.ui.foundation.ui_preview_item import UIWidgetPreviewItem


class UIPreviewCanvas(QtWidgets.QGraphicsView):
    """UI预览画布 - 支持多设备、可交互拖拽"""
    
    # 信号：控件位置改变
    widget_moved = QtCore.pyqtSignal(str, float, float)  # widget_id, x, y
    # 信号：控件大小改变
    widget_resized = QtCore.pyqtSignal(str, float, float)  # widget_id, width, height
    # 信号：控件选中
    widget_selected = QtCore.pyqtSignal(str)  # widget_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 场景
        self.scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene)
        
        # 当前设备尺寸
        self.device_width = 1920
        self.device_height = 1080
        
        # 控件图形项字典
        self.widget_items: Dict[str, UIWidgetPreviewItem] = {}
        
        # 当前选中的控件（支持多选）
        self.selected_widget_ids: set = set()
        self.selected_widget_id: Optional[str] = None  # 主选中控件（用于兼容）
        
        # 网格设置
        self.grid_size = 20
        self.show_grid = True
        
        # 吸附设置
        self.snap_to_grid = True
        self.snap_threshold = 10
        
        # 设置视图属性
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)  # 启用橡皮筋框选
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRubberBandSelectionMode(QtCore.Qt.ItemSelectionMode.IntersectsItemShape)
        
        # 中键拖拽相关
        self.is_panning = False
        self.last_pan_point = QtCore.QPoint()
        
        # 初始化画布
        self._init_canvas()
    
    def _init_canvas(self) -> None:
        """初始化画布"""
        # 清空场景
        self.scene.clear()
        self.widget_items.clear()
        
        # 设置场景大小
        margin = 100
        self.scene.setSceneRect(
            -margin, -margin,
            self.device_width + margin * 2,
            self.device_height + margin * 2
        )
        
        # 绘制设备边框（背景交由全局网格渲染负责）
        device_rect = QtCore.QRectF(0, 0, self.device_width, self.device_height)
        device_item = self.scene.addRect(
            device_rect,
            QtGui.QPen(QtGui.QColor(Colors.BORDER_DARK), 2),
            QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush),
        )
        device_item.setZValue(-100)
        
        # 适应视图
        self.fitInView(device_rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self.scale(0.8, 0.8)  # 稍微缩小以显示边距
    
    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:  # noqa: N802
        """使用全局主题网格作为画布背景。"""
        if self.show_grid:
            ThemeManager.draw_grid_background(painter, rect, self.grid_size)
    
    def set_device(self, width: int, height: int) -> None:
        """设置设备尺寸"""
        self.device_width = width
        self.device_height = height
        self._init_canvas()
        
        # 重新添加所有控件
        for widget_id, item in list(self.widget_items.items()):
            config = item.config
            self.widget_items.pop(widget_id)
            self.add_widget_preview(config)
    
    def add_widget_preview(self, config: dict) -> None:
        """添加控件预览"""
        widget_id = config["widget_id"]
        
        # 创建预览项
        item = UIWidgetPreviewItem(config, self)
        item.setPos(config["position"][0], config["position"][1])
        item.setZValue(config.get("layer_index", 0))
        # 根据初始可见控制显示
        item.setVisible(config.get("initial_visible", True))
        
        # 添加到场景
        self.scene.addItem(item)
        self.widget_items[widget_id] = item
    
    def update_widget_preview(self, widget_id: str, config: dict) -> None:
        """更新控件预览"""
        if widget_id in self.widget_items:
            item = self.widget_items[widget_id]
            item.update_config(config)
            item.setVisible(config.get("initial_visible", True))
    
    def remove_widget_preview(self, widget_id: str) -> None:
        """移除控件预览"""
        if widget_id in self.widget_items:
            item = self.widget_items[widget_id]
            self.scene.removeItem(item)
            del self.widget_items[widget_id]
    
    def select_widget(self, widget_id: Optional[str], multi_select: bool = False) -> None:
        """选中控件
        
        Args:
            widget_id: 控件ID，None表示取消所有选中
            multi_select: 是否多选模式（Ctrl+点击）
        """
        if widget_id is None:
            # 取消所有选中
            for wid in list(self.selected_widget_ids):
                if wid in self.widget_items:
                    self.widget_items[wid].set_selected(False)
            self.selected_widget_ids.clear()
            self.selected_widget_id = None
            return
        
        if multi_select:
            # 多选模式：切换选中状态
            if widget_id in self.selected_widget_ids:
                self.selected_widget_ids.remove(widget_id)
                if widget_id in self.widget_items:
                    self.widget_items[widget_id].set_selected(False)
                # 如果移除的是主选中，更新主选中
                if widget_id == self.selected_widget_id:
                    self.selected_widget_id = next(iter(self.selected_widget_ids)) if self.selected_widget_ids else None
            else:
                self.selected_widget_ids.add(widget_id)
                if widget_id in self.widget_items:
                    self.widget_items[widget_id].set_selected(True)
                self.selected_widget_id = widget_id
        else:
            # 单选模式：取消之前所有选中，选中新控件
            for wid in list(self.selected_widget_ids):
                if wid in self.widget_items:
                    self.widget_items[wid].set_selected(False)
            self.selected_widget_ids.clear()
            
            self.selected_widget_ids.add(widget_id)
            self.selected_widget_id = widget_id
            if widget_id in self.widget_items:
                self.widget_items[widget_id].set_selected(True)
        
        # 发射选中信号（只发射主选中控件）
        if self.selected_widget_id:
            self.widget_selected.emit(self.selected_widget_id)

    def select_widget_silent(self, widget_id: Optional[str]) -> None:
        """选中控件（不发射信号，避免递归）"""
        # 取消之前的所有选中
        for wid in list(self.selected_widget_ids):
            if wid in self.widget_items:
                self.widget_items[wid].set_selected(False)
        self.selected_widget_ids.clear()
        
        # 选中新控件
        if widget_id:
            self.selected_widget_ids.add(widget_id)
            self.selected_widget_id = widget_id
            if widget_id in self.widget_items:
                self.widget_items[widget_id].set_selected(True)
        else:
            self.selected_widget_id = None
    
    def clear_preview(self) -> None:
        """清空预览"""
        self.widget_items.clear()
        self._init_canvas()

    def fit_device(self) -> None:
        """适配设备矩形到视图"""
        device_rect = QtCore.QRectF(0, 0, self.device_width, self.device_height)
        self.fitInView(device_rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
    
    def snap_to_grid_value(self, value: float) -> float:
        """吸附到网格"""
        if self.snap_to_grid:
            return round(value / self.grid_size) * self.grid_size
        return value
    
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """鼠标滚轮事件 - 用于缩放"""
        from app.ui.foundation.interaction_helpers import handle_wheel_zoom_for_view
        handle_wheel_zoom_for_view(self, event, base_factor_per_step=1.15, min_scale=0.2, max_scale=5.0)
    
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标按下事件 - 中/右键拖拽画布，左键框选"""
        if event.button() in (
            QtCore.Qt.MouseButton.MiddleButton,
            QtCore.Qt.MouseButton.RightButton,
        ):
            self.is_panning = True
            self.last_pan_point = event.pos()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
        elif event.button() == QtCore.Qt.MouseButton.LeftButton:
            # 检查是否点击在控件上
            item = self.itemAt(event.pos())
            if item and isinstance(item, UIWidgetPreviewItem):
                # 点击在控件上，让控件处理
                super().mousePressEvent(event)
            else:
                # 点击在空白处，启用框选
                # 如果没有按 Ctrl，清除之前的选中
                if not (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
                    self.select_widget(None)
                super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标移动事件 - 中键拖拽画布"""
        if self.is_panning:
            delta = event.pos() - self.last_pan_point
            self.last_pan_point = event.pos()
            
            # 移动视图
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标释放事件 - 停止拖拽，处理框选"""
        if event.button() in (
            QtCore.Qt.MouseButton.MiddleButton,
            QtCore.Qt.MouseButton.RightButton,
        ):
            self.is_panning = False
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            event.accept()
        elif event.button() == QtCore.Qt.MouseButton.LeftButton:
            # 处理框选结果
            selected_items = self.scene.selectedItems()
            if selected_items:
                # 框选到了控件
                for graphics_item in selected_items:
                    if isinstance(graphics_item, UIWidgetPreviewItem):
                        widget_id = graphics_item.config["widget_id"]
                        if widget_id not in self.selected_widget_ids:
                            self.selected_widget_ids.add(widget_id)
                            graphics_item.set_selected(True)
                            # 更新主选中（最后一个）
                            self.selected_widget_id = widget_id
                # 发射主选中的信号
                if self.selected_widget_id:
                    self.widget_selected.emit(self.selected_widget_id)
            super().mouseReleaseEvent(event)
        else:
            super().mouseReleaseEvent(event)

