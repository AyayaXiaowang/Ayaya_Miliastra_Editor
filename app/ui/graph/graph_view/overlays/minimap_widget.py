from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

if TYPE_CHECKING:
    pass


class MiniMapWidget(QtWidgets.QWidget):
    """小地图组件 - 显示整个节点图的缩略视图"""
    
    def __init__(self, parent_view: 'QtWidgets.QGraphicsView', scene, parent=None):
        super().__init__(parent or parent_view.viewport())
        self.parent_view = parent_view
        self.main_scene = scene
        
        self.setFixedSize(200, 150)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 拖拽状态
        self.dragging = False
        self.drag_start_pos = None
        
        # 样式
        self.background_color = QtGui.QColor(40, 40, 40, 200)
        self.viewport_rect_color = QtGui.QColor(100, 150, 255, 120)
        self.viewport_border_color = QtGui.QColor(100, 150, 255, 255)
        
        # 缓存的场景边界（用于稳定小地图显示）
        self._cached_scene_rect: QtCore.QRectF = None
        self._update_cached_rect()
        
        # 渲染缓存与节流（避免每次绘制都完整渲染场景）
        self._cached_scene_pixmap: QtGui.QPixmap | None = None
        self._cache_dirty: bool = True
        self._rebuild_timer = QtCore.QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.timeout.connect(self._rebuild_cache)
        
        # 监听场景变化，合并触发缓存重建
        if hasattr(self.main_scene, "changed"):
            self.main_scene.changed.connect(self._schedule_cache_rebuild)
        if hasattr(self.main_scene, "sceneRectChanged"):
            self.main_scene.sceneRectChanged.connect(self._schedule_cache_rebuild)
    
    def _update_cached_rect(self) -> None:
        """更新缓存的场景边界（动态显示所有节点的实际范围）"""
        if not self.main_scene:
            return
        
        # 获取所有节点的实际边界
        items_rect = self.main_scene.itemsBoundingRect()
        if items_rect.isEmpty():
            # 使用默认的小区域（而不是之前的大区域）
            self._cached_scene_rect = QtCore.QRectF(-200, -200, 400, 400)
            return
        
        # 添加适当的边距（让节点不贴边，但不过度扩展）
        margin = 200
        new_rect = items_rect.adjusted(-margin, -margin, margin, margin)
        
        # 始终使用实际节点边界，动态更新小地图显示范围
        # 这样小地图会实时反映节点的实际分布情况
        self._cached_scene_rect = new_rect
    
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """绘制小地图（使用缓存的场景缩略图 + 实时视口矩形叠加）"""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        # 背景与边框
        painter.fillRect(self.rect(), self.background_color)
        painter.setPen(QtGui.QPen(QtGui.QColor(80, 80, 80), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        
        if not self.main_scene:
            return
        
        # 若缓存无效，调度一次重建（合并 100ms 内的变化）
        if self._cache_dirty or self._cached_scene_pixmap is None:
            self._schedule_cache_rebuild()
        
        # 绘制缓存的场景缩略图
        if self._cached_scene_pixmap is not None:
            painter.drawPixmap(0, 0, self._cached_scene_pixmap)
        
        # 叠加当前可视区域矩形（仅计算叠加，不重渲染主场景）
        scene_rect = self._cached_scene_rect
        if scene_rect is None or scene_rect.isEmpty():
            return
        minimap_padding = 5
        minimap_rect = self.rect().adjusted(minimap_padding, minimap_padding, -minimap_padding, -minimap_padding)
        scale_x = minimap_rect.width() / scene_rect.width()
        scale_y = minimap_rect.height() / scene_rect.height()
        scale = min(scale_x, scale_y)
        scaled_scene_width = scene_rect.width() * scale
        scaled_scene_height = scene_rect.height() * scale
        offset_x = minimap_padding + (minimap_rect.width() - scaled_scene_width) / 2
        offset_y = minimap_padding + (minimap_rect.height() - scaled_scene_height) / 2
        viewport_scene_rect = self.parent_view.mapToScene(self.parent_view.viewport().rect()).boundingRect()
        viewport_mini_x = (viewport_scene_rect.x() - scene_rect.x()) * scale + offset_x
        viewport_mini_y = (viewport_scene_rect.y() - scene_rect.y()) * scale + offset_y
        viewport_mini_w = viewport_scene_rect.width() * scale
        viewport_mini_h = viewport_scene_rect.height() * scale
        viewport_mini_rect = QtCore.QRectF(viewport_mini_x, viewport_mini_y, viewport_mini_w, viewport_mini_h)
        painter.fillRect(viewport_mini_rect, self.viewport_rect_color)
        painter.setPen(QtGui.QPen(self.viewport_border_color, 2))
        painter.drawRect(viewport_mini_rect)

    def _schedule_cache_rebuild(self) -> None:
        """调度重建小地图场景缓存（100ms 防抖，按“最后一次变更”触发）。

        使用 trailing-edge 防抖策略：每次场景变更都会重启计时器，只有在连续 100ms
        内没有新的变更时才真正重建缓存，避免长时间拖动或批量操作期间反复全图渲染。
        """
        self._cache_dirty = True
        # QTimer.start 会在计时器已激活时自动重置，等效于“延后执行”
        self._rebuild_timer.start(100)

    def _rebuild_cache(self) -> None:
        """重建小地图的场景渲染缓存"""
        if not self.main_scene:
            return
        # 更新边界一次（避免在 paintEvent 里每帧获取 itemsBoundingRect）
        self._update_cached_rect()
        scene_rect = self._cached_scene_rect
        if scene_rect is None or scene_rect.isEmpty():
            self._cached_scene_pixmap = None
            self._cache_dirty = False
            self.update()
            return
        # 构建与小地图同尺寸的位图并将场景渲染进去
        image = QtGui.QImage(self.width(), self.height(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtGui.QColor(0, 0, 0, 0))
        image_painter = QtGui.QPainter(image)
        # 背景与边框在正常绘制时已覆盖，这里仅渲染场景到内边距区域
        minimap_padding = 5
        minimap_rect = QtCore.QRectF(minimap_padding, minimap_padding, self.width() - 2 * minimap_padding, self.height() - 2 * minimap_padding)
        scale_x = minimap_rect.width() / scene_rect.width()
        scale_y = minimap_rect.height() / scene_rect.height()
        scale = min(scale_x, scale_y)
        scaled_scene_width = scene_rect.width() * scale
        scaled_scene_height = scene_rect.height() * scale
        offset_x = minimap_padding + (minimap_rect.width() - scaled_scene_width) / 2
        offset_y = minimap_padding + (minimap_rect.height() - scaled_scene_height) / 2
        target_rect = QtCore.QRectF(offset_x, offset_y, scaled_scene_width, scaled_scene_height)
        image_painter.setClipRect(minimap_rect)
        # 直接按计算后的目标矩形渲染一次主场景
        self.main_scene.render(image_painter, target_rect, scene_rect)
        image_painter.end()
        self._cached_scene_pixmap = QtGui.QPixmap.fromImage(image)
        self._cache_dirty = False
        # 刷新以显示新缓存
        self.update()
    
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标按下 - 开始拖拽或跳转"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_start_pos = event.pos()
            self._jump_to_position(event.pos())
            event.accept()
    
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标移动 - 拖拽跳转"""
        if self.dragging:
            self._jump_to_position(event.pos())
            event.accept()
    
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标释放 - 结束拖拽"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            event.accept()
    
    def _jump_to_position(self, mini_map_pos: QtCore.QPoint) -> None:
        """根据小地图上的点击位置跳转主视图"""
        if not self.main_scene:
            return
        
        # 使用缓存的场景边界（与绘制时一致）
        scene_rect = self._cached_scene_rect
        if scene_rect is None or scene_rect.isEmpty():
            return
        
        # 使用与paintEvent完全相同的计算逻辑
        minimap_padding = 5
        minimap_rect = self.rect().adjusted(minimap_padding, minimap_padding, -minimap_padding, -minimap_padding)
        
        # 计算缩放比例（保持宽高比）
        scale_x = minimap_rect.width() / scene_rect.width()
        scale_y = minimap_rect.height() / scene_rect.height()
        scale = min(scale_x, scale_y)
        
        # 计算缩放后的场景大小
        scaled_scene_width = scene_rect.width() * scale
        scaled_scene_height = scene_rect.height() * scale
        
        # 计算偏移，使场景在小地图中居中
        offset_x = minimap_padding + (minimap_rect.width() - scaled_scene_width) / 2
        offset_y = minimap_padding + (minimap_rect.height() - scaled_scene_height) / 2
        
        # 将小地图坐标转换为场景坐标
        # 反向公式：场景坐标 = (小地图坐标 - 偏移) / 缩放比例 + 场景起点
        scene_x = (mini_map_pos.x() - offset_x) / scale + scene_rect.x()
        scene_y = (mini_map_pos.y() - offset_y) / scale + scene_rect.y()
        
        # 跳转到场景坐标
        self.parent_view.centerOn(scene_x, scene_y)
    
    def update_viewport_rect(self) -> None:
        """更新可视区域矩形"""
        self.update()
    
    def reset_cached_rect(self) -> None:
        """重置缓存的边界（删除节点后可能需要）"""
        self._cached_scene_rect = None
        self._update_cached_rect()
        self.update()

