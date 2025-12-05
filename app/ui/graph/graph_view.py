from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, Qt

from ui.graph.graph_view.animation.view_transform_animation import ViewTransformAnimation
from ui.graph.graph_view.overlays.minimap_widget import MiniMapWidget
from ui.graph.graph_view.overlays.ruler_overlay_painter import RulerOverlayPainter
from ui.graph.graph_view.controllers.interaction_controller import GraphViewInteractionController
from ui.graph.graph_view.navigation.viewport_navigator import ViewportNavigator
from ui.graph.graph_view.highlight.highlight_service import HighlightService
from ui.graph.graph_view.context.add_node_menu_bridge import AddNodeMenuBridge
from ui.graph.graph_view.top_right.controls_manager import TopRightControlsManager
from ui.graph.graph_view.auto_layout.auto_layout_controller import AutoLayoutController
from ui.graph.graph_view.assembly.view_assembly import ViewAssembly
from engine.graph.common import (
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_LISTEN_NODE_TITLE,
)


class GraphView(QtWidgets.QGraphicsView):
    # 新增信号：双击跳转到编辑器
    jump_to_graph_element = pyqtSignal(dict)
    # 新增信号：单击图元素/空白的通用通知（主要用于只读预览场景）
    graph_element_clicked = pyqtSignal(dict)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # 性能：最小更新模式以减少大图下的重绘开销
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        # 性能：缓存背景（坐标标尺/网格等）
        self.setCacheMode(QtWidgets.QGraphicsView.CacheModeFlag.CacheBackground)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # 禁用滚动条：节点图编辑器不显示滚动条，依靠滚轮缩放与拖拽平移
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 使用 NoDrag 模式允许拖拽节点（节点有 ItemIsMovable 标志）
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        
        # 交互控制器（管理所有输入事件与状态）
        self.interaction_controller = GraphViewInteractionController(self)
        
        self.node_library = {}  # 存储节点库
        self.on_add_node_callback = None  # 添加节点的回调函数
        
        # 坐标轴显示设置
        self.show_coordinates = True
        self.coordinate_interval = 250  # 坐标刻度间隔
        
        # 只读模式
        self.read_only = False

        # 仅在需要时启用“单击图元素”信号（例如任务清单右侧只读预览）
        self.enable_click_signals: bool = False
        
        # 节点图作用域
        self.current_scope = "server"  # 默认为服务器作用域
        
        # 小地图
        self.mini_map: Optional[MiniMapWidget] = None
        self.show_mini_map = True  # 是否显示小地图
        
        # 视图变换动画
        self.transform_animation = ViewTransformAnimation(self, self)
        self.enable_smooth_transition = True  # 是否启用平滑过渡
        
        # 节点详情浮窗管理器
        self.overlay_manager = None  # 延迟初始化，等待scene设置后
        
        # 创建自动排版按钮（浮动在右上角）
        self.auto_layout_button = TopRightControlsManager.ensure_auto_layout_button(self)
        self.auto_layout_button.clicked.connect(self._on_auto_layout_clicked)
        
        # 允许外部在右上角放置一个自定义操作按钮（例如：预览中的"编辑"）
        self.extra_top_right_button: Optional[QtWidgets.QWidget] = None
        # 自动排版完成后的回调（由控制器注入），用于例如刷新持久化缓存
        self.on_auto_layout_completed = None

        TopRightControlsManager.update_position(self)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """滚轮事件 - 委托给交互控制器"""
        if self.interaction_controller.handle_wheel(event):
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标按下事件 - 委托给交互控制器"""
        handled = self.interaction_controller.handle_mouse_press(event)
        if handled:
            # 需要伪造左键事件以启动拖拽
            fake = QtGui.QMouseEvent(
                QtCore.QEvent.Type.MouseButtonPress,
                event.position(),
                QtCore.Qt.MouseButton.LeftButton,
                QtCore.Qt.MouseButton.LeftButton,
                event.modifiers()
            )
            super().mousePressEvent(fake)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标释放事件 - 委托给交互控制器"""
        handled = self.interaction_controller.handle_mouse_release(event)
        if handled:
            # 需要伪造左键释放事件
            fake = QtGui.QMouseEvent(
                QtCore.QEvent.Type.MouseButtonRelease,
                event.position(),
                QtCore.Qt.MouseButton.LeftButton,
                QtCore.Qt.MouseButton.LeftButton,
                event.modifiers()
            )
            super().mouseReleaseEvent(fake)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def scrollContentsBy(self, dx: int, dy: int) -> None:
        """滚动内容时触发更新 - 委托给交互控制器"""
        super().scrollContentsBy(dx, dy)
        self.interaction_controller.handle_scroll_contents(dx, dy)


    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """按键事件 - 委托给交互控制器"""
        if self.interaction_controller.handle_key_press(event):
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> None:
        """按键释放事件 - 委托给交互控制器"""
        if self.interaction_controller.handle_key_release(event):
            event.accept()
        else:
            super().keyReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        """双击事件 - 委托给交互控制器"""
        if self.interaction_controller.handle_mouse_double_click(event):
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
    
    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        """右键菜单事件：视图仅负责前置判断与委托，具体行为由场景决定。"""
        # 只读模式下禁用右键菜单
        if self.read_only:
            event.accept()
            return

        # 检查是否是拖动后释放（如果按下和释放位置相差超过5像素，认为是拖动）
        if self.interaction_controller.right_button_pressed_pos is not None:
            distance = (event.pos() - self.interaction_controller.right_button_pressed_pos).manhattanLength()
            if distance > 5:
                # 拖动距离超过5像素，不显示菜单
                self.interaction_controller.clear_right_button_pressed_pos()
                event.accept()
                return

        self.interaction_controller.clear_right_button_pressed_pos()

        current_scene = self.scene()
        if current_scene is None:
            event.accept()
            return

        scene_pos = self.mapToScene(event.pos())
        item = current_scene.itemAt(scene_pos, QtGui.QTransform())

        # 若场景实现了专用处理接口，则优先交给场景决定具体菜单行为
        handle_context_menu = getattr(current_scene, "handle_view_context_menu", None)
        if callable(handle_context_menu):
            handled_by_scene = handle_context_menu(self, event, scene_pos, item)  # type: ignore[misc]
            if handled_by_scene:
                return

        # 默认回退：交给 Qt 的标准分发逻辑（例如端口自身的 contextMenuEvent）
        super().contextMenuEvent(event)
    
    def _show_add_node_menu(self, global_pos: QtCore.QPoint, scene_pos: QtCore.QPointF, filter_port_type: str = None, is_output: bool = True) -> None:
        """显示添加节点的右键菜单 - 委托给菜单桥接"""
        AddNodeMenuBridge.show_add_node_popup(self, global_pos, scene_pos, filter_port_type, is_output)
    
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """重写绘制事件，在视图坐标系中绘制坐标轴"""
        # 先绘制场景内容
        super().paintEvent(event)
        
        # 委托标尺叠层绘制器绘制坐标轴
        painter = QtGui.QPainter(self.viewport())
        RulerOverlayPainter.paint(self, painter)
        painter.end()
        
        # 每次绘制后确保小地图与右上角浮动控件位置与层级正确
        if self.mini_map:
            ViewAssembly.update_mini_map_position(self)
            self.mini_map.raise_()
        # 在绘制阶段同步右上角浮动按钮的位置，避免在布局切换或父级尺寸变化但未触发
        # resizeEvent 时按钮停留在旧坐标而“看起来消失”的问题。
        TopRightControlsManager.update_position(self)
        TopRightControlsManager.raise_all(self)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        """显示事件：确保浮动控件与小地图正确定位与层级"""
        super().showEvent(event)
        if self.mini_map:
            ViewAssembly.update_mini_map_position(self)
            self.mini_map.raise_()
        TopRightControlsManager.raise_all(self)
    
    # === 导航与视口操作（委托给 ViewportNavigator） ===
    
    def center_on_node(self, node_id: str) -> None:
        """将视图居中到指定节点 - 委托给导航器"""
        ViewportNavigator.center_on_node(self, node_id)
    
    def fit_all(self, use_animation: Optional[bool] = None) -> None:
        """适应所有内容到视图 - 委托给导航器"""
        ViewportNavigator.fit_all(self, use_animation=use_animation)
    
    def focus_on_node(self, node_id: str, margin_ratio: float = 1.0, *, use_animation: Optional[bool] = None) -> None:
        """聚焦并缩放到单个节点 - 委托给导航器"""
        ViewportNavigator.focus_on_node(self, node_id, margin_ratio, use_animation=use_animation)
    
    def focus_on_nodes_and_edge(
        self,
        src_node_id: str,
        dst_node_id: str,
        edge_id: str = None,
        *,
        use_animation: Optional[bool] = None,
    ) -> None:
        """聚焦并缩放到两个节点及其连线 - 委托给导航器"""
        ViewportNavigator.focus_on_nodes_and_edge(
            self,
            src_node_id,
            dst_node_id,
            edge_id,
            use_animation=use_animation,
        )
    
    def _execute_focus_on_rect(self, focus_rect: QtCore.QRectF, max_scale: float = 1.5, use_animation: bool = None, padding_ratio: float = 1.0) -> None:
        """执行聚焦到指定矩形区域 - 委托给导航器"""
        ViewportNavigator.execute_focus_on_rect(self, focus_rect, max_scale, use_animation, padding_ratio)
    
    # === 高亮与灰显（委托给 HighlightService） ===
    
    def highlight_node(self, node_id: str) -> None:
        """高亮显示指定节点 - 委托给高亮服务"""
        HighlightService.highlight_node(self, node_id)
    
    def highlight_edge(self, edge_id: str, is_flow_edge: bool = None) -> None:
        """高亮显示指定连线 - 委托给高亮服务"""
        HighlightService.highlight_edge(self, edge_id, is_flow_edge)

    def highlight_nodes_and_edge(self, first_node_id: str, second_node_id: str, edge_id: Optional[str] = None, src_port: Optional[str] = None, dst_port: Optional[str] = None) -> None:
        """一次性高亮两个节点及连线 - 委托给高亮服务"""
        HighlightService.highlight_nodes_and_edge(self, first_node_id, second_node_id, edge_id, src_port, dst_port)
    
    def clear_highlights(self) -> None:
        """清除所有高亮 - 委托给高亮服务"""
        HighlightService.clear_highlights(self)
    
    def highlight_port(self, node_id: str, port_name: str, is_input: bool) -> None:
        """高亮显示指定端口 - 委托给高亮服务"""
        HighlightService.highlight_port(self, node_id, port_name, is_input)
    
    def dim_unrelated_items(self, focused_node_ids: list, focused_edge_ids: list) -> None:
        """将非焦点元素变灰 - 委托给高亮服务"""
        HighlightService.dim_unrelated_items(self, focused_node_ids, focused_edge_ids)
    
    def restore_all_opacity(self) -> None:
        """恢复所有元素的透明度 - 委托给高亮服务"""
        HighlightService.restore_all_opacity(self)
    
    # === 视图装配与布局（委托给 ViewAssembly 和 TopRightControlsManager） ===
    
    def setScene(self, scene) -> None:
        """设置场景 - 委托给装配器"""
        super().setScene(scene)
        ViewAssembly.attach_scene(self, scene)
    
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        """窗口调整大小 - 委托给装配器"""
        super().resizeEvent(event)
        ViewAssembly.on_resize(self, event)

    def set_extra_top_right_button(self, widget: QtWidgets.QWidget) -> None:
        """设置右上角的额外操作按钮 - 委托给控件管理器"""
        TopRightControlsManager.set_extra_button(self, widget)
    
    # === 自动排版（委托给 AutoLayoutController） ===
    
    def _on_auto_layout_clicked(self) -> None:
        """自动排版按钮点击事件 - 委托给自动排版控制器"""
        AutoLayoutController.run(self)
