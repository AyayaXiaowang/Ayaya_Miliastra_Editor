"""连线图形项"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import Optional, TYPE_CHECKING

from app.ui.graph.graph_palette import GraphPalette
if TYPE_CHECKING:
    from app.ui.graph.items.port_item import PortGraphicsItem


class EdgeGraphicsItem(QtWidgets.QGraphicsPathItem):
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
        # 移除选中状态的样式,避免显示虚线框
        option.state &= ~QtWidgets.QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)

    def update_path(self) -> None:
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

