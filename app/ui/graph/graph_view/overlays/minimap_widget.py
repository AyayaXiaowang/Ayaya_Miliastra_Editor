from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from engine.configs.settings import settings as _settings_ui

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

    def _get_model_counts(self) -> tuple[int, int]:
        """返回 (node_count, edge_count)。

        说明：小地图的“是否降级渲染”依赖图规模；这里避免触碰 QGraphicsItem，
        直接读取 model 字典长度即可。
        """
        scene = self.main_scene
        model = getattr(scene, "model", None) if scene is not None else None
        nodes = getattr(model, "nodes", None) if model is not None else None
        edges = getattr(model, "edges", None) if model is not None else None
        node_count = len(nodes) if isinstance(nodes, dict) else 0
        edge_count = len(edges) if isinstance(edges, dict) else 0
        return (int(node_count), int(edge_count))

    def _should_use_simplified_render(self) -> bool:
        """是否对小地图启用“模型级简化渲染”（避免 scene.render 全量遍历）。"""
        node_count, edge_count = self._get_model_counts()
        node_threshold = int(getattr(_settings_ui, "GRAPH_MINIMAP_SIMPLIFY_NODE_THRESHOLD", 500))
        edge_threshold = int(getattr(_settings_ui, "GRAPH_MINIMAP_SIMPLIFY_EDGE_THRESHOLD", 900))
        return bool(node_count >= node_threshold or edge_count >= edge_threshold)

    def _current_rebuild_debounce_ms(self) -> int:
        """根据图规模选择小地图缓存重建的防抖间隔。"""
        if self._should_use_simplified_render():
            return int(getattr(_settings_ui, "GRAPH_MINIMAP_SIMPLIFY_DEBOUNCE_MS", 240))
        return int(getattr(_settings_ui, "GRAPH_MINIMAP_DEBOUNCE_MS", 100))

    def _compute_cached_rect_from_model(self) -> QtCore.QRectF:
        """基于 GraphModel.nodes 的 pos 估算内容边界（避免 itemsBoundingRect）。"""
        scene = self.main_scene
        model = getattr(scene, "model", None) if scene is not None else None
        nodes = getattr(model, "nodes", None) if model is not None else None
        if not isinstance(nodes, dict) or not nodes:
            return QtCore.QRectF()

        min_x = 1e18
        min_y = 1e18
        max_x = -1e18
        max_y = -1e18
        for node in nodes.values():
            pos = getattr(node, "pos", None)
            if not isinstance(pos, (list, tuple)) or len(pos) < 2:
                continue
            x = float(pos[0])
            y = float(pos[1])
            if x < min_x:
                min_x = x
            if y < min_y:
                min_y = y
            if x > max_x:
                max_x = x
            if y > max_y:
                max_y = y

        if min_x > max_x or min_y > max_y:
            return QtCore.QRectF()

        approx_w = float(getattr(_settings_ui, "GRAPH_MINIMAP_APPROX_NODE_WIDTH", 280.0))
        approx_h = float(getattr(_settings_ui, "GRAPH_MINIMAP_APPROX_NODE_HEIGHT", 140.0))
        margin = float(getattr(_settings_ui, "GRAPH_MINIMAP_MARGIN", 200.0))

        rect = QtCore.QRectF(
            float(min_x),
            float(min_y),
            float(max(1.0, (max_x - min_x) + approx_w)),
            float(max(1.0, (max_y - min_y) + approx_h)),
        )
        return rect.adjusted(-margin, -margin, margin, margin)
    
    def _update_cached_rect(self) -> None:
        """更新缓存的场景边界（动态显示所有节点的实际范围）"""
        if not self.main_scene:
            return

        # 超大图：避免 itemsBoundingRect/scene.render 触发全量遍历，改为基于 model 的估算边界。
        if self._should_use_simplified_render():
            model_rect = self._compute_cached_rect_from_model()
            if not model_rect.isEmpty():
                self._cached_scene_rect = model_rect
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

    def _schedule_cache_rebuild(self, *args) -> None:
        """调度重建小地图场景缓存（100ms 防抖，按“最后一次变更”触发）。

        使用 trailing-edge 防抖策略：每次场景变更都会重启计时器，只有在连续 100ms
        内没有新的变更时才真正重建缓存，避免长时间拖动或批量操作期间反复全图渲染。

        参数:
            *args: 兼容 Qt 信号（如 `QGraphicsScene.changed(QList[QRectF])`、
                   `sceneRectChanged(QRectF)`）携带的额外 payload；此处不使用。
        """
        self._cache_dirty = True
        # QTimer.start 会在计时器已激活时自动重置，等效于“延后执行”
        self._rebuild_timer.start(self._current_rebuild_debounce_ms())

    def _render_simplified_model_snapshot(
        self,
        painter: QtGui.QPainter,
        *,
        target_rect: QtCore.QRectF,
        scene_rect: QtCore.QRectF,
    ) -> None:
        """将 GraphModel 的节点分布以“点阵”方式绘制到小地图缓存中。"""
        scene = self.main_scene
        model = getattr(scene, "model", None) if scene is not None else None
        nodes = getattr(model, "nodes", None) if model is not None else None
        if not isinstance(nodes, dict) or not nodes:
            return
        if scene_rect.isEmpty() or target_rect.isEmpty():
            return

        approx_w = float(getattr(_settings_ui, "GRAPH_MINIMAP_APPROX_NODE_WIDTH", 280.0))
        approx_h = float(getattr(_settings_ui, "GRAPH_MINIMAP_APPROX_NODE_HEIGHT", 140.0))
        dot_px = float(getattr(_settings_ui, "GRAPH_MINIMAP_NODE_DOT_PX", 2.0))
        dot_px = max(1.0, min(6.0, dot_px))

        scale = float(target_rect.width() / scene_rect.width()) if float(scene_rect.width()) != 0.0 else 1.0

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        color = QtGui.QColor(180, 180, 180, 180)
        painter.setBrush(color)

        # 超极端规模保护：避免一次性画太多点（小地图像素有限，过量点阵没有信息增益）。
        max_points = int(getattr(_settings_ui, "GRAPH_MINIMAP_MAX_POINTS", 20000))
        stride = 1
        if len(nodes) > max_points and max_points > 0:
            stride = max(1, len(nodes) // max_points)

        idx = 0
        for node in nodes.values():
            idx += 1
            if stride > 1 and (idx % stride) != 0:
                continue
            pos = getattr(node, "pos", None)
            if not isinstance(pos, (list, tuple)) or len(pos) < 2:
                continue
            x = float(pos[0]) + approx_w * 0.5
            y = float(pos[1]) + approx_h * 0.5
            mx = (x - float(scene_rect.x())) * scale + float(target_rect.x())
            my = (y - float(scene_rect.y())) * scale + float(target_rect.y())
            painter.drawRect(QtCore.QRectF(float(mx), float(my), float(dot_px), float(dot_px)))

        painter.restore()

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

        # 渲染策略：
        # - 常规图：使用 QGraphicsScene.render 生成缩略图（更精确）
        # - 超大图：改为“模型级点阵渲染”（仅节点分布），避免 scene.render 的全量遍历导致卡顿
        if self._should_use_simplified_render():
            self._render_simplified_model_snapshot(
                image_painter,
                target_rect=target_rect,
                scene_rect=scene_rect,
            )
        else:
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
        # 仅更新边界不足以保证“缩略图内容”同步：
        # - 在批量装配场景/首次打开等场景下，小地图可能已在“空场景”时生成过一次缓存位图；
        # - 若后续场景内容变化未触发 changed/sceneRectChanged（例如更新被上层临时禁用），
        #   只更新 rect 会导致仍然绘制旧的空位图，从而看起来“小地图是空的”。
        # 因此这里显式失效位图缓存并调度一次重建，保证范围与内容一致。
        self._cached_scene_pixmap = None
        self._cache_dirty = True
        self._schedule_cache_rebuild()
        self.update()

