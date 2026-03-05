"""连线图形项"""

from __future__ import annotations

import time

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import Optional, TYPE_CHECKING

from app.ui.graph.graph_palette import GraphPalette
from engine.configs.settings import settings as _settings_ui
if TYPE_CHECKING:
    from app.ui.graph.items.port_item import PortGraphicsItem


class EdgeGraphicsItem(QtWidgets.QGraphicsPathItem):
    """节点图连线图形项。

    注意：Qt 默认会基于 QGraphicsPathItem.shape() 判定命中与选择区域。
    为避免“点击连线附近也被选中”的误触，这里显式收敛命中区域宽度，使其更贴近视觉线条。
    """

    # 命中区域宽度（单位：场景坐标）。该宽度只影响选择/点击命中，不影响绘制线宽。
    _HIT_TEST_STROKE_WIDTH_DATA: float = 1.5
    _HIT_TEST_STROKE_WIDTH_FLOW: float = 3.0
    _HIT_TEST_STROKE_WIDTH_MIN: float = 1.5

    def __init__(self, src: PortGraphicsItem, dst: PortGraphicsItem, edge_id: str):
        super().__init__()
        self.src = src
        self.dst = dst
        self.edge_id = edge_id
        # 将连线置于节点之下
        self.setZValue(5)
        # 设置为可选中
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        # 根据是否为流程端口设置不同的颜色
        self.is_flow_edge = self.src.is_flow and self.dst.is_flow
        self._highlight_color: Optional[QtGui.QColor] = None  # 多链高亮颜色(覆盖默认)
        self._update_pen()
        self.update_path()

        # 命中形状缓存：shape() 可能在鼠标命中与框选中被频繁调用，缓存能减少重复 stroker 成本。
        self._cached_hit_shape: Optional[QtGui.QPainterPath] = None
        self._cached_hit_shape_source_path: Optional[QtGui.QPainterPath] = None
        self._cached_hit_shape_width: Optional[float] = None
    
    def _update_pen(self) -> None:
        """更新画笔样式"""
        if self._highlight_color is not None:
            # 多链高亮颜色优先
            color = self._highlight_color
            width = 5 if not self.is_flow_edge else 6
        elif self.isSelected():
            # 选中时根据边类型显示不同的高亮颜色
            if self.is_flow_edge:
                # 流程边:明亮的橙红色
                color = QtGui.QColor(GraphPalette.EDGE_FLOW_SELECTED)  # 明亮的橙红色
                width = 6
            else:
                # 数据边:明亮的青色
                color = QtGui.QColor(GraphPalette.EDGE_DATA_SELECTED)  # 明亮的青色
                width = 5
        elif self.is_flow_edge:
            # 检查是否是分支连线("是"或"否")
            if self.src.name == '是':
                # "是"分支:绿色
                color = QtGui.QColor(GraphPalette.EDGE_BRANCH_YES)  # 绿色
                width = 4
            elif self.src.name == '否':
                # "否"分支:红色
                color = QtGui.QColor(GraphPalette.EDGE_BRANCH_NO)  # 红色
                width = 4
            else:
                # 主流程线:明亮的黄色,更粗
                color = QtGui.QColor(GraphPalette.EDGE_FLOW_MAIN)  # 金黄色
                width = 4
        else:
            # 数据线:蓝色调,更细
            color = QtGui.QColor(GraphPalette.EDGE_DATA)  # 蓝色调
            width = 2
        self.setPen(QtGui.QPen(color, width))
        # 线宽变化会影响命中宽度策略，需失效缓存
        self._invalidate_hit_shape_cache()
        self.update()  # 触发重绘
    
    def set_highlight_color(self, color: Optional[QtGui.QColor]) -> None:
        """设置覆盖高亮颜色(None 表示清除)"""
        self._highlight_color = color
        self._update_pen()
    
    def itemChange(self, change, value):
        # 选中状态改变时更新画笔
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            # 延迟更新,确保选中状态已经改变
            QtCore.QTimer.singleShot(0, self._update_pen)
        return super().itemChange(change, value)
    
    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        """重写paint方法,移除选中时的虚线框"""
        scene_ref = self.scene()
        monitor = getattr(scene_ref, "_perf_monitor", None) if scene_ref is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        track = getattr(monitor, "track_slowest", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.paint.edge.calls", 1)

        # LOD：低倍率缩放时隐藏非高亮/非选中的连线，显著降低超大图的绘制成本
        if bool(getattr(_settings_ui, "GRAPH_LOD_ENABLED", True)):
            t0 = time.perf_counter_ns() if monitor is not None else 0
            scale_hint = float(painter.worldTransform().m11())
            edge_min_scale = float(getattr(_settings_ui, "GRAPH_LOD_EDGE_MIN_SCALE", 0.22))
            if (
                scale_hint < edge_min_scale
                and (not self.isSelected())
                and (self._highlight_color is None)
            ):
                if monitor is not None and callable(accum):
                    accum("items.paint.edge.lod_gate", int(time.perf_counter_ns() - int(t0)))
                    dt_total_ns = int(time.perf_counter_ns() - int(t_total0))
                    accum("items.paint.edge.total", dt_total_ns)
                    if callable(track):
                        track(f"edge:{self.edge_id}", dt_total_ns)
                return
            if monitor is not None and callable(accum):
                accum("items.paint.edge.lod_gate", int(time.perf_counter_ns() - int(t0)))

        # 移除选中状态的样式,避免显示虚线框
        option.state &= ~QtWidgets.QStyle.StateFlag.State_Selected
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            super().paint(painter, option, widget)
            accum("items.paint.edge.super", int(time.perf_counter_ns() - int(t0)))
            dt_total_ns = int(time.perf_counter_ns() - int(t_total0))
            accum("items.paint.edge.total", dt_total_ns)
            if callable(track):
                track(f"edge:{self.edge_id}", dt_total_ns)
        else:
            super().paint(painter, option, widget)

    def _invalidate_hit_shape_cache(self) -> None:
        self._cached_hit_shape = None
        self._cached_hit_shape_source_path = None
        self._cached_hit_shape_width = None

    def _get_hit_test_stroke_width(self) -> float:
        """获取用于命中测试的描边宽度（与绘制 pen 宽度解耦）。"""
        base_width = (
            self._HIT_TEST_STROKE_WIDTH_FLOW if self.is_flow_edge else self._HIT_TEST_STROKE_WIDTH_DATA
        )
        pen_width = float(self.pen().widthF()) if self.pen() is not None else 0.0
        # 命中宽度不应小于视觉线宽的 75%，否则会出现“线看得见但点不到”的体验问题。
        width_by_pen = pen_width * 0.75 if pen_width > 0.0 else 0.0
        return max(self._HIT_TEST_STROKE_WIDTH_MIN, base_width, width_by_pen)

    def shape(self) -> QtGui.QPainterPath:
        """返回用于命中测试的形状路径。

        目的：将连线的“可选中区域”控制得更接近线条本身，减少误触。
        """
        # LOD：低倍率缩放时降低命中测试成本（非高亮/非选中连线直接返回空 shape）
        scene_ref_for_perf = self.scene()
        monitor = getattr(scene_ref_for_perf, "_perf_monitor", None) if scene_ref_for_perf is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        track = getattr(monitor, "track_slowest", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.shape.edge.calls", 1)

        if bool(getattr(_settings_ui, "GRAPH_LOD_ENABLED", True)):
            scene_ref = self.scene()
            scale_hint = float(getattr(scene_ref, "view_scale_hint", 1.0) or 1.0) if scene_ref is not None else 1.0
            hit_min_scale = float(getattr(_settings_ui, "GRAPH_LOD_EDGE_HITTEST_MIN_SCALE", 0.28))
            if (
                scale_hint < hit_min_scale
                and (not self.isSelected())
                and (self._highlight_color is None)
            ):
                if monitor is not None and callable(accum):
                    accum("items.shape.edge.lod_skip", int(time.perf_counter_ns() - int(t_total0)))
                return QtGui.QPainterPath()

        current_path = self.path()
        if current_path.isEmpty():
            return QtGui.QPainterPath()

        hit_width = self._get_hit_test_stroke_width()
        if (
            self._cached_hit_shape is not None
            and self._cached_hit_shape_source_path == current_path
            and self._cached_hit_shape_width == hit_width
        ):
            if callable(inc):
                inc("items.shape.edge.cache_hit", 1)
            if monitor is not None and callable(accum):
                dt_ns = int(time.perf_counter_ns() - int(t_total0))
                accum("items.shape.edge.total", dt_ns)
                if callable(track):
                    track(f"edge.shape:{self.edge_id}", dt_ns)
            return self._cached_hit_shape

        if callable(inc):
            inc("items.shape.edge.cache_miss", 1)
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(hit_width)
        # 命中形状采用圆角端帽/圆角连接，避免尖角扩大命中范围
        stroker.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            hit_shape = stroker.createStroke(current_path)
            accum("items.shape.edge.stroker", int(time.perf_counter_ns() - int(t0)))
        else:
            hit_shape = stroker.createStroke(current_path)

        self._cached_hit_shape = hit_shape
        self._cached_hit_shape_source_path = QtGui.QPainterPath(current_path)
        self._cached_hit_shape_width = hit_width
        if monitor is not None and callable(accum):
            dt_ns = int(time.perf_counter_ns() - int(t_total0))
            accum("items.shape.edge.total", dt_ns)
            if callable(track):
                track(f"edge.shape:{self.edge_id}", dt_ns)
        return hit_shape

    def update_path(self) -> None:
        scene_ref = self.scene()
        monitor = getattr(scene_ref, "_perf_monitor", None) if scene_ref is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        track = getattr(monitor, "track_slowest", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.update_path.edge.calls", 1)

        # 获取端口圆心在场景中的绝对位置
        src_port_center = self.src.scenePos()
        dst_port_center = self.dst.scenePos()
        
        # 获取起点:从源端口圆心向右延伸到节点矩形边框的交点
        src_node_item = self.src.node_item
        src_node_rect_scene = src_node_item.sceneBoundingRect()
        # 输出端口:从圆心向右到矩形右边界
        start_x = src_node_rect_scene.right()  # 节点矩形的右边界
        start_y = src_port_center.y()
        start = QtCore.QPointF(start_x, start_y)
        
        # 获取终点:从目标端口圆心向左延伸到节点矩形边框的交点
        dst_node_item = self.dst.node_item
        dst_node_rect_scene = dst_node_item.sceneBoundingRect()
        # 输入端口:从圆心向左到矩形左边界
        end_x = dst_node_rect_scene.left()  # 节点矩形的左边界
        end_y = dst_port_center.y()
        end = QtCore.QPointF(end_x, end_y)
        
        # 创建贝塞尔曲线路径
        p = QtGui.QPainterPath(start)
        dx = abs(end.x() - start.x()) * 0.5
        c1 = QtCore.QPointF(start.x() + dx, start.y())
        c2 = QtCore.QPointF(end.x() - dx, end.y())
        p.cubicTo(c1, c2, end)
        self.setPath(p)
        # 路径变化会影响命中形状
        self._invalidate_hit_shape_cache()
        if monitor is not None and callable(accum):
            dt_ns = int(time.perf_counter_ns() - int(t_total0))
            accum("items.update_path.edge.total", dt_ns)
            if callable(track):
                track(f"edge.update_path:{self.edge_id}", dt_ns)

