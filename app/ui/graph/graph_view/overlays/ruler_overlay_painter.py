from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6 import QtCore, QtGui

from app.ui.foundation.theme_manager import Colors

if TYPE_CHECKING:
    from PyQt6 import QtWidgets


class RulerOverlayPainter:
    """标尺叠层绘制器
    
    负责在GraphView视图坐标系中绘制坐标轴标尺（不受缩放影响）。
    """
    
    @staticmethod
    def paint(view: 'QtWidgets.QGraphicsView', painter: QtGui.QPainter) -> None:
        """在视图坐标系中绘制坐标轴标尺
        
        Args:
            view: 目标图形视图
            painter: 已初始化的画笔对象（绘制目标为viewport）
        """
        if not hasattr(view, 'show_coordinates') or not view.show_coordinates:
            return
        
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        # 标尺的固定像素大小（不受缩放影响）
        ruler_height = 30
        ruler_width = 80
        ruler_color = QtGui.QColor(Colors.CANVAS_RULER_BACKGROUND)
        ruler_color.setAlpha(230)  # 稍微透明
        text_color = QtGui.QColor(Colors.CANVAS_RULER_TEXT)
        line_color = QtGui.QColor(Colors.CANVAS_RULER_LINE)
        
        painter.setFont(QtGui.QFont('Consolas', 9))
        
        viewport_rect = view.viewport().rect()
        
        # 绘制顶部X轴标尺（固定30像素高）
        top_ruler_rect = QtCore.QRect(0, 0, viewport_rect.width(), ruler_height)
        painter.fillRect(top_ruler_rect, ruler_color)
        
        # 绘制X坐标刻度
        # 计算场景坐标范围
        left_scene = view.mapToScene(QtCore.QPoint(ruler_width, 0)).x()
        right_scene = view.mapToScene(QtCore.QPoint(viewport_rect.width(), 0)).x()

        # 根据当前缩放动态合并刻度：保证视图中相邻标注至少有最小像素间距
        # 顶部文字宽度为100px（以中心对齐绘制），因此最小间距设置为100像素以避免重叠
        coordinate_interval = getattr(view, 'coordinate_interval', 250)
        viewport_transform = view.viewportTransform()
        pixel_per_unit_x = math.hypot(viewport_transform.m11(), viewport_transform.m12())
        if pixel_per_unit_x == 0.0:
            pixel_per_unit_x = abs(view.mapFromScene(QtCore.QPointF(1, 0)).x() - view.mapFromScene(QtCore.QPointF(0, 0)).x())
        min_x_label_spacing_px = 100.0
        effective_interval_x = coordinate_interval
        if pixel_per_unit_x > 0.0:
            while effective_interval_x * pixel_per_unit_x < min_x_label_spacing_px:
                effective_interval_x *= 2

        left_coord = int(left_scene / effective_interval_x) * effective_interval_x
        x_scene = left_coord
        
        painter.setPen(QtGui.QPen(line_color, 1))
        while x_scene <= right_scene:
            # 将场景坐标转换为视图坐标
            x_view = view.mapFromScene(QtCore.QPointF(x_scene, 0)).x()
            
            if x_view >= ruler_width:  # 不与左侧标尺重叠
                # 绘制刻度线
                painter.drawLine(x_view, 0, x_view, 10)
                
                # 绘制坐标文本
                painter.setPen(text_color)
                text_rect = QtCore.QRect(x_view - 50, 12, 100, ruler_height - 12)
                painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignCenter, f"X: {int(x_scene)}")
                painter.setPen(QtGui.QPen(line_color, 1))
            
            x_scene += effective_interval_x
        
        # 绘制左侧Y轴标尺（固定80像素宽）
        left_ruler_rect = QtCore.QRect(0, ruler_height, ruler_width, viewport_rect.height() - ruler_height)
        painter.fillRect(left_ruler_rect, ruler_color)
        
        # 绘制Y坐标刻度
        top_scene = view.mapToScene(QtCore.QPoint(0, ruler_height)).y()
        bottom_scene = view.mapToScene(QtCore.QPoint(0, viewport_rect.height())).y()

        # 左侧Y轴最小间距以文字高度为基准（约20px），留出余量设置为28像素
        pixel_per_unit_y = math.hypot(viewport_transform.m21(), viewport_transform.m22())
        if pixel_per_unit_y == 0.0:
            pixel_per_unit_y = abs(view.mapFromScene(QtCore.QPointF(0, 1)).y() - view.mapFromScene(QtCore.QPointF(0, 0)).y())
        min_y_label_spacing_px = 28.0
        effective_interval_y = coordinate_interval
        if pixel_per_unit_y > 0.0:
            while effective_interval_y * pixel_per_unit_y < min_y_label_spacing_px:
                effective_interval_y *= 2

        top_coord = int(top_scene / effective_interval_y) * effective_interval_y
        y_scene = top_coord
        
        while y_scene <= bottom_scene:
            # 将场景坐标转换为视图坐标
            y_view = view.mapFromScene(QtCore.QPointF(0, y_scene)).y()
            
            if y_view >= ruler_height:  # 不与顶部标尺重叠
                # 绘制刻度线
                painter.setPen(QtGui.QPen(line_color, 1))
                painter.drawLine(0, y_view, 10, y_view)
                
                # 绘制坐标文本
                painter.setPen(text_color)
                text_rect = QtCore.QRect(12, y_view - 10, ruler_width - 12, 20)
                painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft, f"Y: {int(y_scene)}")
            
            y_scene += effective_interval_y
        
        # 绘制左上角的原点指示
        corner_rect = QtCore.QRect(0, 0, ruler_width, ruler_height)
        painter.fillRect(corner_rect, QtGui.QColor(Colors.CANVAS_RULER_CORNER_BACKGROUND))
        painter.setPen(text_color)
        painter.drawText(corner_rect, QtCore.Qt.AlignmentFlag.AlignCenter, "坐标")

