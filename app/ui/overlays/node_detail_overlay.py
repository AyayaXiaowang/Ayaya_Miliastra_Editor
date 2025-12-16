"""节点详情浮窗组件

当两个节点距离很远时，在视图角落显示节点副本，方便查看连接细节。
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import Optional, Set


class NodeDetailOverlay(QtWidgets.QWidget):
    """节点详情浮窗
    
    显示节点的完整图形副本，并可以高亮特定端口。
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 设置窗口属性
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 数据
        self.node_item = None  # NodeGraphicsItem的引用
        self.highlighted_ports = set()  # {port_name}
        self.scale_factor = 1.0  # 缩放因子
        
        # 透明度控制（用于淡入淡出动画）
        self._opacity = 0.0
        
        # 版本控制，防止快速切换时的延迟操作影响新内容
        self._display_version = 0
        
        # 样式
        self.background_color = QtGui.QColor(30, 30, 30, 230)
        self.border_color = QtGui.QColor(100, 150, 255, 255)
        self.highlight_flow_color = QtGui.QColor(255, 200, 0, 255)  # 流程端口高亮色
        self.highlight_data_color = QtGui.QColor(0, 255, 150, 255)  # 数据端口高亮色
        
        # 设置默认大小（将根据viewport大小动态调整）
        self.default_width = 400
        self.default_height = 300
        self.resize(self.default_width, self.default_height)
        
        # 淡入淡出动画（与缩放动画时长保持一致）
        self._fade_animation = QtCore.QPropertyAnimation(self, b"opacity")
        self._fade_animation.setDuration(1000)  # 1000毫秒，与缩放动画同步
        self._fade_animation.setEasingCurve(QtCore.QEasingCurve.Type.InOutCubic)  # 使用与缩放相同的缓动
        self._fade_animation.finished.connect(self._on_animation_finished)
        
        # 记录当前动画目标（fade_in 或 fade_out）
        self._animation_target = None
    
    def set_node(self, node_item, highlighted_ports: Set[str] = None):
        """设置要显示的节点
        
        Args:
            node_item: NodeGraphicsItem实例
            highlighted_ports: 要高亮的端口名称集合
        """
        # 递增版本号，使之前的延迟操作失效
        self._display_version += 1
        
        # 检查节点对象有效性
        if node_item:
            _ = node_item.isSelected()

        self.node_item = node_item
        self.highlighted_ports = highlighted_ports or set()
        
        # 计算缩放因子，确保节点适应窗口
        self._recalculate_scale_factor()
        
        self.update()
    
    def _recalculate_scale_factor(self):
        """重新计算缩放因子，确保节点适应当前窗口大小"""
        if not self.node_item:
            return
        
        node_rect = self.node_item.boundingRect()
        # 留出边距
        margin = 20
        available_width = self.width() - margin * 2
        available_height = self.height() - margin * 2
        
        scale_x = available_width / node_rect.width()
        scale_y = available_height / node_rect.height()
        self.scale_factor = min(scale_x, scale_y, 1.5)  # 最大1.5倍
    
    def clear(self):
        """清除显示"""
        self.node_item = None
        self.highlighted_ports.clear()
        self.update()
    
    def get_opacity(self):
        """获取透明度"""
        return self._opacity
    
    def set_opacity(self, value):
        """设置透明度并触发重绘"""
        self._opacity = max(0.0, min(1.0, value))
        self.update()
    
    # Qt属性，用于动画
    opacity = QtCore.pyqtProperty(float, get_opacity, set_opacity)
    
    def fade_in(self):
        """淡入显示"""
        # 停止当前动画
        if self._fade_animation.state() == QtCore.QAbstractAnimation.State.Running:
            self._fade_animation.stop()
        
        # 如果widget不可见，先显示并重置透明度为0
        if not self.isVisible():
            self._opacity = 0.0
            super().show()
        
        # 记录当前版本号
        current_version = self._display_version
        
        # 设置动画目标
        self._animation_target = ('fade_in', current_version)
        self._fade_animation.setStartValue(self._opacity)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.start()
    
    def fade_out(self):
        """淡出隐藏"""
        # 停止当前动画
        if self._fade_animation.state() == QtCore.QAbstractAnimation.State.Running:
            self._fade_animation.stop()
        
        # 记录当前版本号
        current_version = self._display_version
        
        # 设置动画目标，确保从当前透明度开始淡出
        self._animation_target = ('fade_out', current_version)
        self._fade_animation.setStartValue(self._opacity)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.start()
    
    def _on_animation_finished(self):
        """动画完成时的回调"""
        if not self._animation_target:
            return
        
        # 检查版本号，如果版本已变化说明有新操作，忽略此回调
        target_type, target_version = self._animation_target
        if target_version != self._display_version:
            return
        
        # 淡出完成后真正隐藏widget
        if target_type == 'fade_out':
            super().hide()
        self._animation_target = None
    
    def update_size(self, viewport_size: QtCore.QSize):
        """根据viewport大小动态调整浮窗大小
        
        Args:
            viewport_size: viewport的尺寸
        """
        # 计算目标大小（viewport的25%）
        target_width = int(viewport_size.width() * 0.25)
        target_height = int(viewport_size.height() * 0.25)
        
        # 限制最大值
        target_width = min(target_width, 600)
        target_height = min(target_height, 450)
        
        # 限制最小值（降低最小值以适应小窗口，但仍保证基本可见性）
        target_width = max(target_width, 200)
        target_height = max(target_height, 150)
        
        # 应用新尺寸
        self.setFixedSize(target_width, target_height)
        
        # 重新计算缩放因子，确保节点适应新的窗口大小
        self._recalculate_scale_factor()
        
        # 重绘浮窗
        self.update()
    
    def paintEvent(self, event: QtGui.QPaintEvent):
        """绘制节点副本"""
        if not self.node_item:
            return

        # 检查节点对象是否还有效（防止快速切换导致的C++对象已删除错误）
        _ = self.node_item.isSelected()

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # 应用透明度
        painter.setOpacity(self._opacity)

        # 绘制背景
        painter.fillRect(self.rect(), self.background_color)

        # 绘制边框
        painter.setPen(QtGui.QPen(self.border_color, 2))
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

        # 计算居中位置
        node_rect = self.node_item.boundingRect()
        scaled_width = node_rect.width() * self.scale_factor
        scaled_height = node_rect.height() * self.scale_factor

        offset_x = (self.width() - scaled_width) / 2
        offset_y = (self.height() - scaled_height) / 2

        # 设置变换
        painter.translate(offset_x, offset_y)
        painter.scale(self.scale_factor, self.scale_factor)

        # 绘制节点本体
        self.node_item.paint(painter, QtWidgets.QStyleOptionGraphicsItem(), self)

        # 绘制端口（端口是节点的子项，需要手动绘制）
        self._draw_ports(painter)

        # 绘制高亮端口
        painter.resetTransform()
        painter.translate(offset_x, offset_y)
        painter.scale(self.scale_factor, self.scale_factor)

        for port_name in self.highlighted_ports:
            self._draw_highlighted_port(painter, port_name)
    
    def _draw_ports(self, painter: QtGui.QPainter):
        """绘制所有端口
        
        Args:
            painter: 画笔（已应用缩放变换）
        """
        if not self.node_item:
            return

        # 绘制每个端口
        for port in self.node_item.iter_all_ports():
            # 计算端口在节点图中的位置
            port_pos = port.scenePos() - self.node_item.scenePos()

            # 绘制端口圆点
            radius = 4
            painter.setBrush(QtGui.QBrush(QtGui.QColor(100, 100, 255)))
            painter.setPen(QtGui.QPen(QtGui.QColor(50, 50, 200), 1))
            painter.drawEllipse(QtCore.QPointF(port_pos.x(), port_pos.y()), radius, radius)
    
    def _draw_highlighted_port(self, painter: QtGui.QPainter, port_name: str):
        """绘制高亮端口
        
        Args:
            painter: 画笔
            port_name: 端口名称
        """
        if not self.node_item:
            return
        
        port_item = self.node_item.get_port_by_name(port_name)
        if not port_item:
            return
        
        # 判断是流程端口还是数据端口：优先使用端口图形项标记，回退到全局规则
        if hasattr(port_item, 'is_flow'):
            is_flow_port = bool(getattr(port_item, 'is_flow'))
        else:
            from engine.utils.graph.graph_utils import is_flow_port_name
            is_flow_port = is_flow_port_name(str(port_name))
        
        # 选择高亮颜色
        highlight_color = self.highlight_flow_color if is_flow_port else self.highlight_data_color
        
        # 获取端口位置和大小
        port_pos = port_item.pos()
        port_rect = port_item.boundingRect()
        
        # 绘制高亮光晕
        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        
        # 外层光晕（半透明）
        glow_color = QtGui.QColor(highlight_color)
        glow_color.setAlpha(80)
        painter.setBrush(glow_color)
        glow_rect = QtCore.QRectF(
            port_pos.x() + port_rect.x() - 6,
            port_pos.y() + port_rect.y() - 6,
            port_rect.width() + 12,
            port_rect.height() + 12
        )
        painter.drawEllipse(glow_rect)
        
        # 内层高亮（明亮）
        painter.setBrush(highlight_color)
        highlight_rect = QtCore.QRectF(
            port_pos.x() + port_rect.x() - 3,
            port_pos.y() + port_rect.y() - 3,
            port_rect.width() + 6,
            port_rect.height() + 6
        )
        painter.drawEllipse(highlight_rect)
        
        painter.restore()


class NodeDetailOverlayManager(QtCore.QObject):
    """节点详情浮窗管理器
    
    管理两个浮窗的显示和隐藏，以及位置计算。
    """
    
    def __init__(self, parent_view):
        super().__init__(parent_view)
        self.parent_view = parent_view
        
        # 创建两个浮窗
        self.left_overlay = NodeDetailOverlay(parent_view.viewport())
        self.right_overlay = NodeDetailOverlay(parent_view.viewport())
        
        # 初始隐藏
        self.left_overlay.hide()
        self.right_overlay.hide()
        
        # 距离阈值（场景单位）
        self.distance_threshold = 800
        
        # 位置更新节流定时器（避免频繁更新导致性能问题）
        self._update_timer = QtCore.QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._update_positions)
        
        # 操作版本控制，防止快速切换时的冲突
        self._operation_version = 0
        
        # 待执行的清除定时器引用
        self._pending_clear_timer = None
        self._pending_clear_debouncer = None

        # 当前显示的节点ID（避免持有已删除的图形项引用）
        self._node1_id: Optional[str] = None
        self._node2_id: Optional[str] = None
    
    def show_node_pair(self, node1_id: str, node2_id: str, 
                       port1_name: str = None, port2_name: str = None):
        """显示一对节点的详情浮窗
        
        Args:
            node1_id: 第一个节点ID
            node2_id: 第二个节点ID
            port1_name: 第一个节点要高亮的端口（可选）
            port2_name: 第二个节点要高亮的端口（可选）
        """
        # 递增版本号，使之前的操作失效
        self._operation_version += 1
        
        # 立即停止所有正在进行的fade动画
        if self.left_overlay._fade_animation.state() == QtCore.QAbstractAnimation.State.Running:
            self.left_overlay._fade_animation.stop()
        if self.right_overlay._fade_animation.state() == QtCore.QAbstractAnimation.State.Running:
            self.right_overlay._fade_animation.stop()
        
        # 取消待执行的清除操作
        if self._pending_clear_timer is not None:
            self._pending_clear_timer.stop()
            self._pending_clear_timer = None
        
        if not self.parent_view.scene():
            return
        
        # 获取节点图形项
        node1_item = self.parent_view.scene().get_node_item(node1_id)
        node2_item = self.parent_view.scene().get_node_item(node2_id)
        
        if not node1_item or not node2_item:
            return
        
        # 记录当前节点ID，用于后续在场景中重新解析
        self._node1_id = node1_id
        self._node2_id = node2_id

        # 计算两个节点的距离
        pos1 = node1_item.scenePos()
        pos2 = node2_item.scenePos()
        distance = QtCore.QLineF(pos1, pos2).length()
        
        # 如果距离小于阈值，不显示浮窗
        if distance < self.distance_threshold:
            self.hide()
            return
        
        # 更新浮窗大小（根据viewport大小动态调整）
        viewport_size = self.parent_view.viewport().size()
        self.left_overlay.update_size(viewport_size)
        self.right_overlay.update_size(viewport_size)
        
        # 设置节点和高亮端口
        highlight1 = {port1_name} if port1_name else set()
        highlight2 = {port2_name} if port2_name else set()
        
        self.left_overlay.set_node(node1_item, highlight1)
        self.right_overlay.set_node(node2_item, highlight2)
        
        # 更新位置
        self._update_positions()
        
        # 淡入显示浮窗
        self.left_overlay.fade_in()
        self.right_overlay.fade_in()
    
    def hide(self):
        """隐藏所有浮窗"""
        # 递增版本号，使之前的操作失效
        self._operation_version += 1
        current_version = self._operation_version
        
        # 取消旧的清除定时器/防抖
        if self._pending_clear_debouncer is not None:
            self._pending_clear_debouncer.cancel()
        self._pending_clear_timer = None
        
        # 开始淡出动画
        self.left_overlay.fade_out()
        self.right_overlay.fade_out()
        
        # 清除操作延迟到淡出完成后（使用 Debouncer 统一防抖）
        from app.ui.foundation.debounce import Debouncer
        if self._pending_clear_debouncer is None:
            self._pending_clear_debouncer = Debouncer(self)
        self._pending_clear_debouncer.debounce(1050, lambda: self._delayed_clear(current_version))
    
    def _delayed_clear(self, target_version):
        """延迟清除浮窗内容（在淡出动画完成后）
        
        Args:
            target_version: 目标版本号，只有当前版本匹配时才执行清除
        """
        # 检查版本号，如果版本已变化说明有新操作，忽略此清除
        if target_version != self._operation_version:
            return
        
        self.left_overlay.clear()
        self.right_overlay.clear()
        self._pending_clear_timer = None
        # 清空当前节点ID，避免后续更新时错误访问
        self._node1_id = None
        self._node2_id = None
    
    def stop_all_animations(self):
        """立即停止所有动画（用于任务切换时）"""
        # 递增版本号，使所有待执行的操作失效
        self._operation_version += 1
        
        # 立即停止所有fade动画
        if self.left_overlay._fade_animation.state() == QtCore.QAbstractAnimation.State.Running:
            self.left_overlay._fade_animation.stop()
        if self.right_overlay._fade_animation.state() == QtCore.QAbstractAnimation.State.Running:
            self.right_overlay._fade_animation.stop()
        
        # 取消待执行的清除操作
        if self._pending_clear_debouncer is not None:
            self._pending_clear_debouncer.cancel()
            self._pending_clear_timer = None
        
        # 立即隐藏浮窗（不使用动画）
        self.left_overlay.hide()
        self.right_overlay.hide()
        
        # 清除内容
        self.left_overlay.clear()
        self.right_overlay.clear()
        # 同步清空节点ID
        self._node1_id = None
        self._node2_id = None
    
    def request_position_update(self):
        """请求更新浮窗位置（带节流机制，避免性能问题）
        
        此方法会在16ms内最多触发一次位置更新，即最高60fps。
        适合在视图变换事件（滚轮、拖拽）中频繁调用。
        """
        # 只在浮窗可见时更新
        if not (self.left_overlay.isVisible() or self.right_overlay.isVisible()):
            return
        
        # 如果定时器未激活，立即启动（16ms后执行）
        if not self._update_timer.isActive():
            self._update_timer.start(16)  # 16ms = 60fps
    
    def _update_positions(self):
        """更新浮窗位置（根据节点实际位置动态计算）"""
        scene = self.parent_view.scene()
        if not scene or not self._node1_id or not self._node2_id:
            return
        # 通过场景根据ID获取最新的图形项，避免引用已删除对象
        node1_item = scene.get_node_item(self._node1_id)
        node2_item = scene.get_node_item(self._node2_id)
        if not node1_item or not node2_item:
            # 任一节点不存在时隐藏浮窗
            self.hide()
            return
        
        # 获取节点在场景中的位置
        node1_scene_pos = node1_item.scenePos()
        node2_scene_pos = node2_item.scenePos()
        
        # 判断左右节点（X坐标小的是左节点）
        if node1_scene_pos.x() > node2_scene_pos.x():
            left_node_item = node2_item
            right_node_item = node1_item
            left_overlay = self.right_overlay
            right_overlay = self.left_overlay
        else:
            left_node_item = node1_item
            right_node_item = node2_item
            left_overlay = self.left_overlay
            right_overlay = self.right_overlay
        
        # 计算左节点浮窗位置：在节点左边
        left_pos = self._calculate_overlay_position(
            left_node_item, left_overlay, position_preference='left'
        )
        left_overlay.move(left_pos)
        
        # 计算右节点浮窗位置：在节点右边
        right_pos = self._calculate_overlay_position(
            right_node_item, right_overlay, position_preference='right'
        )
        right_overlay.move(right_pos)
    
    def _calculate_overlay_position(self, node_item, overlay, position_preference: str) -> QtCore.QPoint:
        """计算浮窗位置
        
        Args:
            node_item: 节点图形项
            overlay: 浮窗对象
            position_preference: 位置偏好 ('left' 或 'right')
        
        Returns:
            浮窗在viewport中的位置
        """
        # 1. 获取节点在视图中的矩形
        node_scene_rect = node_item.sceneBoundingRect()
        node_view_polygon = self.parent_view.mapFromScene(node_scene_rect)
        node_view_rect = node_view_polygon.boundingRect()
        
        # 2. 根据偏好计算位置（左边或右边）
        margin = 20  # 与节点的间距
        if position_preference == 'left':
            x = node_view_rect.left() - overlay.width() - margin
            y = node_view_rect.center().y() - overlay.height() // 2
        else:  # 'right'
            x = node_view_rect.right() + margin
            y = node_view_rect.center().y() - overlay.height() // 2
        
        # 3. 检查是否超出viewport边界，如果超出则调整到上方或下方
        viewport_rect = self.parent_view.viewport().rect()
        if x < 0 or x + overlay.width() > viewport_rect.width():
            # 左右放不下，放到上方或下方
            x = node_view_rect.center().x() - overlay.width() // 2
            if y < 0:  # 上方空间不足，放下方
                y = node_view_rect.bottom() + margin
            else:  # 放上方
                y = node_view_rect.top() - overlay.height() - margin
        
        # 4. 确保不超出viewport边界
        x = max(10, min(x, viewport_rect.width() - overlay.width() - 10))
        y = max(10, min(y, viewport_rect.height() - overlay.height() - 10))
        
        return QtCore.QPoint(int(x), int(y))
    
    def update_on_resize(self):
        """视图大小改变时更新大小和位置"""
        if self.left_overlay.isVisible() or self.right_overlay.isVisible():
            # 更新大小
            viewport_size = self.parent_view.viewport().size()
            self.left_overlay.update_size(viewport_size)
            self.right_overlay.update_size(viewport_size)
            # 更新位置
            self._update_positions()

