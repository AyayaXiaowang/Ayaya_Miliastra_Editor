from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6 import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from PyQt6 import QtWidgets


class ViewTransformAnimation(QtCore.QObject):
    """视图变换动画辅助类
    
    用于平滑过渡视图的缩放和位置。
    """
    finished = QtCore.pyqtSignal()
    
    def __init__(self, view: 'QtWidgets.QGraphicsView', parent=None):
        super().__init__(parent)
        self.view = view
        
        # 动画参数
        self.start_scale = 1.0
        self.end_scale = 1.0
        self.start_center = QtCore.QPointF(0, 0)
        self.end_center = QtCore.QPointF(0, 0)
        
        # 使用定时器驱动动画
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._update_animation)
        
        self.elapsed_time = 0
        self.duration = 1000  # 1秒
        self.is_running = False

        # 动画期间临时改写锚点（避免 AnchorUnderMouse 影响 setTransform + centerOn 的稳定性）
        self._saved_transformation_anchor: QtWidgets.QGraphicsView.ViewportAnchor | None = None
        self._saved_resize_anchor: QtWidgets.QGraphicsView.ViewportAnchor | None = None

    def stop(self) -> None:
        """停止正在运行的过渡动画，并恢复视图锚点。

        说明：
        - 动画期间会将 view 的 transformationAnchor/resizeAnchor 临时切到 NoAnchor；
        - 若中途取消动画，必须恢复锚点，否则后续滚轮缩放将不再以鼠标为中心。
        """
        if not self.is_running:
            return
        self.timer.stop()
        self.is_running = False
        self._restore_view_anchors()
    
    def start_transition(self, target_rect: QtCore.QRectF, duration: int = 1000, max_scale: float = 1.5, padding_ratio: float = 1.0):
        """开始过渡动画
        
        Args:
            target_rect: 目标聚焦矩形（场景坐标）
            duration: 动画时长（毫秒）
            max_scale: 最大缩放限制
            padding_ratio: 额外缩放系数（<1.0 进一步缩小，>1.0 放大），用于留出可视边距
        """
        # 若上一次动画仍在运行，先停止并恢复视图状态，避免并发写 transform 导致闪烁与抖动。
        self.stop()

        # 保存当前状态
        current_transform = self.view.transform()
        start_scale = current_transform.m11()
        start_center = self.view.mapToScene(self.view.viewport().rect().center())
        
        # 计算目标状态
        viewport_size = self.view.viewport().size()
        if viewport_size.width() <= 0 or viewport_size.height() <= 0:
            return
        
        # 计算目标缩放比例
        scene_rect_width = target_rect.width()
        scene_rect_height = target_rect.height()
        
        if scene_rect_width <= 0 or scene_rect_height <= 0:
            return
        
        scale_x = viewport_size.width() / scene_rect_width
        scale_y = viewport_size.height() / scene_rect_height
        target_scale = min(scale_x, scale_y) * padding_ratio
        
        # 限制最大缩放
        end_scale = min(target_scale, max_scale)
        end_center = target_rect.center()

        # 视图锚点：动画期间强制使用 NoAnchor，避免缩放锚点参与导致“镜头漂移”。
        self._prepare_view_anchors_for_animation()

        self.start_scale = float(start_scale)
        self.start_center = QtCore.QPointF(start_center)
        self.end_scale = float(end_scale)
        self.end_center = QtCore.QPointF(end_center)
        
        # 启动动画
        self.elapsed_time = 0
        self.duration = duration
        self.is_running = True
        self.timer.start(16)  # 约60fps
    
    def _update_animation(self):
        """更新动画帧"""
        self.elapsed_time += 16
        
        if self.elapsed_time >= self.duration:
            # 动画结束，应用最终状态
            self._apply_transform(1.0)
            self.timer.stop()
            self.is_running = False
            self._restore_view_anchors()
            self.finished.emit()
        else:
            # 计算进度（使用缓动函数）
            progress = self.elapsed_time / self.duration
            eased_progress = self._ease_in_out_cubic(progress)
            
            # 应用插值变换
            self._apply_transform(eased_progress)
    
    def _apply_transform(self, progress: float):
        """应用插值后的变换
        
        Args:
            progress: 动画进度 (0.0 到 1.0)
        """
        # 插值缩放
        current_scale = self.start_scale + (self.end_scale - self.start_scale) * progress
        
        # 插值中心点
        current_center = QtCore.QPointF(
            self.start_center.x() + (self.end_center.x() - self.start_center.x()) * progress,
            self.start_center.y() + (self.end_center.y() - self.start_center.y()) * progress
        )
        
        # 应用变换（直接设置transform矩阵，避免resetTransform导致的闪烁）
        # 创建一个新的transform矩阵，只包含缩放
        from PyQt6.QtGui import QTransform
        transform = QTransform()
        transform.scale(current_scale, current_scale)
        
        # 直接设置transform（不会导致闪烁）
        self.view.setTransform(transform)
        
        # 设置新的中心
        self.view.centerOn(current_center)

        # 关键：动画路径下强制刷新视口与叠层。
        # 说明：切换搜索结果会触发聚焦动画；若只改 transform/centerOn 而不主动请求重绘，
        # Qt 可能使用像素滚动/缓存拷贝优化，导致挂在 viewport 上的叠层（搜索栏等）
        # “跟着画布一起缩放/飞走”的视觉错觉。
        viewport_widget = self.view.viewport()
        if viewport_widget is not None:
            viewport_widget.update()

        search_overlay = getattr(self.view, "search_overlay", None)
        if search_overlay is not None and hasattr(search_overlay, "isVisible") and search_overlay.isVisible():
            if hasattr(search_overlay, "raise_"):
                search_overlay.raise_()
            if hasattr(search_overlay, "update"):
                search_overlay.update()

    def _prepare_view_anchors_for_animation(self) -> None:
        if self._saved_transformation_anchor is None:
            self._saved_transformation_anchor = self.view.transformationAnchor()
        if self._saved_resize_anchor is None:
            self._saved_resize_anchor = self.view.resizeAnchor()
        self.view.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
        self.view.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)

    def _restore_view_anchors(self) -> None:
        if self._saved_transformation_anchor is not None:
            self.view.setTransformationAnchor(self._saved_transformation_anchor)
        if self._saved_resize_anchor is not None:
            self.view.setResizeAnchor(self._saved_resize_anchor)
        self._saved_transformation_anchor = None
        self._saved_resize_anchor = None
    
    @staticmethod
    def _ease_in_out_cubic(t: float) -> float:
        """三次缓动函数（ease-in-out）
        
        Args:
            t: 输入进度 (0.0 到 1.0)
        
        Returns:
            缓动后的进度 (0.0 到 1.0)
        """
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 3) / 2

