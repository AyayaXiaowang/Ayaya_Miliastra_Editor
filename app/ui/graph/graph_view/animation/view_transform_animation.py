from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6 import QtCore, QtGui

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
    
    def start_transition(self, target_rect: QtCore.QRectF, duration: int = 1000, max_scale: float = 1.5, padding_ratio: float = 1.0):
        """开始过渡动画
        
        Args:
            target_rect: 目标聚焦矩形（场景坐标）
            duration: 动画时长（毫秒）
            max_scale: 最大缩放限制
            padding_ratio: 额外缩放系数（<1.0 进一步缩小，>1.0 放大），用于留出可视边距
        """
        # 保存当前状态
        current_transform = self.view.transform()
        self.start_scale = current_transform.m11()
        self.start_center = self.view.mapToScene(self.view.viewport().rect().center())
        
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
        self.end_scale = min(target_scale, max_scale)
        self.end_center = target_rect.center()
        
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

