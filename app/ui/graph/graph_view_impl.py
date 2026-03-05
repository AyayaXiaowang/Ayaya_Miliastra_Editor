from __future__ import annotations

import time
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal, Qt

from app.ui.graph.graph_view.animation.view_transform_animation import ViewTransformAnimation
from app.ui.graph.graph_view.overlays.minimap_widget import MiniMapWidget
from app.ui.graph.graph_view.overlays.graph_perf_overlay import GraphPerfMonitor, GraphPerfOverlay
from app.ui.graph.graph_view.overlays.graph_loading_overlay import GraphLoadingOverlay
from app.ui.graph.graph_view.overlays.ruler_overlay_painter import RulerOverlayPainter
from app.ui.graph.graph_view.overlays.graph_search_overlay import GraphSearchOverlay
from app.ui.graph.graph_view.controllers.interaction_controller import GraphViewInteractionController
from app.ui.graph.graph_view.navigation.viewport_navigator import ViewportNavigator
from app.ui.graph.graph_view.highlight.highlight_service import HighlightService
from app.ui.graph.graph_view.context.add_node_menu_bridge import AddNodeMenuBridge
from app.ui.graph.graph_view.top_right.controls_manager import TopRightControlsManager
from app.ui.graph.graph_view.auto_layout.auto_layout_controller import AutoLayoutController
from app.ui.graph.graph_view.assembly.view_assembly import ViewAssembly
from engine.graph.common import (
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_LISTEN_NODE_TITLE,
)
from app.models.edit_session_capabilities import EditSessionCapabilities
from app.ui.foundation.keymap_store import KeymapStore


class GraphView(QtWidgets.QGraphicsView):
    # 新增信号：双击跳转到编辑器
    jump_to_graph_element = pyqtSignal(dict)
    # 新增信号：单击图元素/空白的通用通知（主要用于只读预览场景）
    graph_element_clicked = pyqtSignal(dict)

    def __init__(self, *args, **kwargs):
        edit_session_capabilities = kwargs.pop("edit_session_capabilities", None)
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

        self._edit_session_capabilities: EditSessionCapabilities = (
            edit_session_capabilities
            if isinstance(edit_session_capabilities, EditSessionCapabilities)
            else EditSessionCapabilities.interactive_preview()
        )
        self._read_only: bool = bool(self._edit_session_capabilities.is_read_only)

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

        # 画布性能面板（默认关闭；在设置页开启后显示）
        self._perf_panel_enabled: bool = False
        self._perf_monitor: GraphPerfMonitor | None = None
        self._perf_overlay: GraphPerfOverlay | None = None

        # 画布内搜索（Ctrl+F）
        self.search_overlay = GraphSearchOverlay(self)
        self._find_shortcut: QtGui.QShortcut | None = None
        self._rebuild_find_shortcut(self._default_find_shortcut_text())
        # 适配全图（Ctrl+0）
        self._fit_all_shortcut: QtGui.QShortcut | None = None
        self._rebuild_fit_all_shortcut(self._default_fit_all_shortcut_text())

        # 加载遮罩：用于超大图加载/自动排版等长任务，避免用户误以为卡死
        self.loading_overlay = GraphLoadingOverlay(self)

        # 创建自动排版按钮（浮动在右上角）
        self.auto_layout_button = TopRightControlsManager.ensure_auto_layout_button(self)
        self.auto_layout_button.clicked.connect(self._on_auto_layout_clicked)

        # 画布搜索按钮：除 Ctrl+F 外提供显式入口
        self.search_button = TopRightControlsManager.ensure_search_button(self)
        self.search_button.clicked.connect(self.open_search_overlay)

        # 允许外部在右上角放置一个自定义操作按钮（例如：预览中的"编辑"）
        self.extra_top_right_button: Optional[QtWidgets.QWidget] = None
        # 允许插件在右上角放置若干扩展控件（位于主按钮与“自动排版”之间）
        self.extra_top_right_extension_widgets: list[QtWidgets.QWidget] = []
        self._extra_top_right_extension_widgets_by_key: dict[str, QtWidgets.QWidget] = {}
        self._extra_top_right_extensions_visible: bool = True
        # 自动排版完成后的回调（由控制器注入），用于例如刷新持久化缓存
        self.on_auto_layout_completed = None

        TopRightControlsManager.update_position(self)
        # 读取设置并按需显示性能面板（默认关闭）
        self.refresh_perf_panel_visibility()

    def refresh_perf_panel_visibility(self) -> None:
        """根据 settings 刷新画布性能面板可见性（立即生效，无需重启）。"""
        from engine.configs.settings import settings as _settings

        enabled = bool(getattr(_settings, "GRAPH_PERF_PANEL_ENABLED", False))
        self._perf_panel_enabled = bool(enabled)

        if enabled:
            if self._perf_monitor is None:
                self._perf_monitor = GraphPerfMonitor(window_size=180)
            if self._perf_overlay is None:
                self._perf_overlay = GraphPerfOverlay(self, monitor=self._perf_monitor)
            self._perf_overlay.start()
            current_scene = self.scene()
            if current_scene is not None:
                setattr(current_scene, "_perf_monitor", self._perf_monitor)
            return

        # disabled
        if self._perf_overlay is not None:
            self._perf_overlay.stop()
        current_scene = self.scene()
        if current_scene is not None:
            setattr(current_scene, "_perf_monitor", None)

    def _default_find_shortcut_text(self) -> str:
        defaults = KeymapStore.get_default_shortcuts("graph_view.find")
        return defaults[0] if defaults else "Ctrl+F"

    def _rebuild_find_shortcut(self, shortcut_text: str) -> None:
        if self._find_shortcut is not None:
            self._find_shortcut.setEnabled(False)
            self._find_shortcut.deleteLater()
            self._find_shortcut = None

        text = str(shortcut_text or "").strip()
        if not text:
            return
        shortcut = QtGui.QShortcut(QtGui.QKeySequence(text), self)
        shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.open_search_overlay)
        self._find_shortcut = shortcut

    def _default_fit_all_shortcut_text(self) -> str:
        defaults = KeymapStore.get_default_shortcuts("graph_view.fit_all")
        return defaults[0] if defaults else "Ctrl+0"

    def _rebuild_fit_all_shortcut(self, shortcut_text: str) -> None:
        if self._fit_all_shortcut is not None:
            self._fit_all_shortcut.setEnabled(False)
            self._fit_all_shortcut.deleteLater()
            self._fit_all_shortcut = None

        text = str(shortcut_text or "").strip()
        if not text:
            return
        shortcut = QtGui.QShortcut(QtGui.QKeySequence(text), self)
        shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.fit_all)
        self._fit_all_shortcut = shortcut

    def apply_keymap_shortcuts(self, keymap_store: object) -> None:
        """由主窗口调用：在快捷键配置变更后刷新 GraphView 内快捷键绑定。"""
        get_primary = getattr(keymap_store, "get_primary_shortcut", None)
        find_shortcut_text = (
            str(get_primary("graph_view.find") or "") if callable(get_primary) else self._default_find_shortcut_text()
        )
        if not find_shortcut_text:
            find_shortcut_text = ""
        self._rebuild_find_shortcut(find_shortcut_text)

        fit_all_shortcut_text = (
            str(get_primary("graph_view.fit_all") or "")
            if callable(get_primary)
            else self._default_fit_all_shortcut_text()
        )
        if not fit_all_shortcut_text:
            fit_all_shortcut_text = ""
        self._rebuild_fit_all_shortcut(fit_all_shortcut_text)

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
                event.modifiers(),
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
                event.modifiers(),
            )
            super().mouseReleaseEvent(fake)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        """滚动内容时触发更新 - 委托给交互控制器"""
        super().scrollContentsBy(dx, dy)
        # Qt 在对象析构/窗口关闭等阶段仍可能触发 scrollContentsBy；
        # 此时 Python wrapper 可能已进入“半销毁”状态，instance dict 字段不再可靠。
        controller = getattr(self, "interaction_controller", None)
        if controller is not None:
            controller.handle_scroll_contents(dx, dy)

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

        # 场景侧右键菜单桥接：GraphScene 必然继承 SceneViewContextMenuMixin。
        from app.ui.scene.view_context_menu_mixin import SceneViewContextMenuMixin

        if isinstance(current_scene, SceneViewContextMenuMixin):
            handled_by_scene = current_scene.handle_view_context_menu(self, event, scene_pos, item)
            if handled_by_scene:
                return

        # 默认回退：交给 Qt 的标准分发逻辑（例如端口自身的 contextMenuEvent）
        super().contextMenuEvent(event)

    def show_add_node_menu(
        self,
        global_pos: QtCore.QPoint,
        scene_pos: QtCore.QPointF,
        filter_port_type: str | None = None,
        is_output: bool = True,
    ) -> None:
        """公开的“添加节点”菜单入口（供场景交互/右键菜单桥接调用）。

        说明：
        - 统一收敛 Scene→View 的调用协议，避免通过 `hasattr(view, "_show_add_node_menu")`
          这类反射式钩子协作。
        """
        self._show_add_node_menu(
            global_pos,
            scene_pos,
            filter_port_type=filter_port_type,
            is_output=is_output,
        )

    def _show_add_node_menu(
        self,
        global_pos: QtCore.QPoint,
        scene_pos: QtCore.QPointF,
        filter_port_type: str = None,
        is_output: bool = True,
    ) -> None:
        """显示添加节点的右键菜单 - 委托给菜单桥接"""
        AddNodeMenuBridge.show_add_node_popup(self, global_pos, scene_pos, filter_port_type, is_output)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """重写绘制事件，在视图坐标系中绘制坐标轴"""
        monitor = self._perf_monitor if (self._perf_panel_enabled and self._perf_monitor is not None) else None
        if monitor is not None:
            monitor.begin_frame()
            t_total0 = time.perf_counter()
            current_scene = self.scene()
            if current_scene is not None:
                # 让场景叠加层也能记录 drawBackground/drawForeground
                setattr(current_scene, "_perf_monitor", monitor)
            with monitor.scope("view.paint.scene"):
                super().paintEvent(event)
        else:
            # 先绘制场景内容
            super().paintEvent(event)

        # 同步当前缩放比例到场景（供 Edge.shape/Port LOD 等“无 option”路径使用）
        current_scene = self.scene()
        if current_scene is not None:
            t0 = time.perf_counter() if monitor is not None else 0.0
            scale_hint = float(self.transform().m11())
            set_hint = getattr(current_scene, "set_view_scale_hint", None)
            if callable(set_hint):
                set_hint(scale_hint)
            else:
                setattr(current_scene, "view_scale_hint", scale_hint)
            if monitor is not None:
                monitor.record_ms("view.paint.scale_hint", (time.perf_counter() - float(t0)) * 1000.0)

        # 委托标尺叠层绘制器绘制坐标轴
        if monitor is not None:
            with monitor.scope("view.paint.ruler"):
                painter = QtGui.QPainter(self.viewport())
                RulerOverlayPainter.paint(self, painter)
                painter.end()
        else:
            painter = QtGui.QPainter(self.viewport())
            RulerOverlayPainter.paint(self, painter)
            painter.end()

        # 每次绘制后确保小地图与右上角浮动控件位置与层级正确
        if self.mini_map:
            if monitor is not None:
                with monitor.scope("view.paint.minimap_position"):
                    ViewAssembly.update_mini_map_position(self)
                    self.mini_map.raise_()
            else:
                ViewAssembly.update_mini_map_position(self)
                self.mini_map.raise_()
        # 在绘制阶段同步右上角浮动按钮的位置，避免在布局切换或父级尺寸变化但未触发
        # resizeEvent 时按钮停留在旧坐标而“看起来消失”的问题。
        if monitor is not None:
            with monitor.scope("view.paint.top_right_controls"):
                TopRightControlsManager.update_position(self)
                TopRightControlsManager.raise_all(self)
        else:
            TopRightControlsManager.update_position(self)
            TopRightControlsManager.raise_all(self)
        if hasattr(self, "search_overlay") and self.search_overlay and self.search_overlay.isVisible():
            if monitor is not None:
                with monitor.scope("view.paint.search_raise"):
                    self.search_overlay.raise_()
            else:
                self.search_overlay.raise_()

        if hasattr(self, "loading_overlay") and self.loading_overlay and self.loading_overlay.isVisible():
            self.loading_overlay.raise_()

        if monitor is not None:
            if self._perf_overlay is not None and self._perf_overlay.isVisible():
                # 确保面板始终位于最上层（不参与 viewport.scroll）
                self._perf_overlay.raise_()
            controller = getattr(self, "interaction_controller", None)
            is_panning = bool(getattr(controller, "is_panning", False)) if controller is not None else False
            monitor.record_ms("view.paint.total", (time.perf_counter() - float(t_total0)) * 1000.0)
            monitor.end_frame(is_panning=bool(is_panning))

    def drawItems(self, painter: QtGui.QPainter, numItems: int, items, options, widget=None) -> None:  # noqa: N802, ANN001
        """视图绘制 items 的入口（用于性能面板拆分 Qt 的 item 绘制阶段）。

        注意：
        - Qt 在 `QGraphicsView.paintEvent` 内会调用该方法；
        - 我们只记录总耗时与本次调用绘制的 item 数量，不做类型遍历，避免统计本身成为瓶颈。
        """
        monitor = self._perf_monitor if (self._perf_panel_enabled and self._perf_monitor is not None) else None
        if monitor is None:
            super().drawItems(painter, numItems, items, options, widget)
            return

        t0 = time.perf_counter_ns()
        inc = getattr(monitor, "inc", None)
        if callable(inc):
            inc("view.drawItems.calls", 1)
            try_items = int(numItems) if isinstance(numItems, int) else 0
            if try_items <= 0 and hasattr(items, "__len__"):
                try_items = int(len(items))  # type: ignore[arg-type]
            if try_items > 0:
                inc("view.drawItems.items", int(try_items))

        super().drawItems(painter, numItems, items, options, widget)

        dt_ns = int(time.perf_counter_ns() - int(t0))
        accum = getattr(monitor, "accum_ns", None)
        if callable(accum):
            accum("view.drawItems.total", dt_ns)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        """显示事件：确保浮动控件与小地图正确定位与层级"""
        super().showEvent(event)
        if self.mini_map:
            ViewAssembly.update_mini_map_position(self)
            self.mini_map.raise_()
        TopRightControlsManager.raise_all(self)
        if self._perf_overlay is not None and self._perf_overlay.isVisible():
            self._perf_overlay.reposition()
            self._perf_overlay.raise_()

    # === 导航与视口操作（委托给 ViewportNavigator） ===

    def center_on_node(self, node_id: str) -> None:
        """将视图居中到指定节点 - 委托给导航器"""
        ViewportNavigator.center_on_node(self, node_id)

    def fit_all(self, use_animation: Optional[bool] = None) -> None:
        """适应所有内容到视图 - 委托给导航器"""
        ViewportNavigator.fit_all(self, use_animation=use_animation)

    def focus_on_node(
        self, node_id: str, margin_ratio: float = 1.0, *, use_animation: Optional[bool] = None
    ) -> None:
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

    def _execute_focus_on_rect(
        self,
        focus_rect: QtCore.QRectF,
        max_scale: float = 1.5,
        use_animation: bool = None,
        padding_ratio: float = 1.0,
    ) -> None:
        """执行聚焦到指定矩形区域 - 委托给导航器"""
        ViewportNavigator.execute_focus_on_rect(self, focus_rect, max_scale, use_animation, padding_ratio)

    # === 高亮与灰显（委托给 HighlightService） ===

    def highlight_node(self, node_id: str) -> None:
        """高亮显示指定节点 - 委托给高亮服务"""
        HighlightService.highlight_node(self, node_id)

    def highlight_edge(self, edge_id: str, is_flow_edge: bool = None) -> None:
        """高亮显示指定连线 - 委托给高亮服务"""
        HighlightService.highlight_edge(self, edge_id, is_flow_edge)

    def highlight_nodes_and_edge(
        self,
        first_node_id: str,
        second_node_id: str,
        edge_id: Optional[str] = None,
        src_port: Optional[str] = None,
        dst_port: Optional[str] = None,
    ) -> None:
        """一次性高亮两个节点及连线 - 委托给高亮服务"""
        HighlightService.highlight_nodes_and_edge(
            self,
            first_node_id,
            second_node_id,
            edge_id,
            src_port,
            dst_port,
        )

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
        # 将能力同步到新场景，避免出现 view/scene 语义分裂
        if scene is not None and hasattr(scene, "set_edit_session_capabilities"):
            scene.set_edit_session_capabilities(self._edit_session_capabilities)
        if hasattr(self, "search_overlay") and self.search_overlay:
            self.search_overlay.on_scene_changed()
        if self._perf_panel_enabled and self._perf_monitor is not None and scene is not None:
            setattr(scene, "_perf_monitor", self._perf_monitor)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        """窗口调整大小 - 委托给装配器"""
        super().resizeEvent(event)
        ViewAssembly.on_resize(self, event)
        if hasattr(self, "search_overlay") and self.search_overlay and self.search_overlay.isVisible():
            self.search_overlay.reposition()
        if hasattr(self, "loading_overlay") and self.loading_overlay and self.loading_overlay.isVisible():
            self.loading_overlay.reposition()
            self.loading_overlay.raise_()
        if self._perf_overlay is not None and self._perf_overlay.isVisible():
            self._perf_overlay.reposition()

    def set_extra_top_right_button(self, widget: QtWidgets.QWidget) -> None:
        """设置右上角的额外操作按钮 - 委托给控件管理器"""
        TopRightControlsManager.set_extra_button(self, widget)

    def ensure_top_right_extension_widget(
        self,
        key: str,
        *,
        create_widget: callable,
        visible: bool = True,
    ) -> QtWidgets.QWidget:
        """确保一个“右上角扩展控件”存在（插件注入用）。

        约定：
        - 扩展控件位于主按钮与“自动排版”之间；
        - 会受 `set_top_right_extensions_visible(False)` 统一隐藏（例如 TODO 预览借用共享画布）。
        """
        stable_key = str(key or "").strip()
        if stable_key == "":
            raise ValueError("extension widget key 不能为空")

        existing = self._extra_top_right_extension_widgets_by_key.get(stable_key)
        if existing is not None:
            existing.setVisible(bool(visible) and self._extra_top_right_extensions_visible)
            TopRightControlsManager.update_position(self)
            return existing

        widget_obj = create_widget(self)
        if not isinstance(widget_obj, QtWidgets.QWidget):
            raise TypeError(
                f"create_widget 必须返回 QWidget（got: {type(widget_obj).__name__}）"
            )
        self._extra_top_right_extension_widgets_by_key[stable_key] = widget_obj
        TopRightControlsManager.add_extension_widget(self, widget_obj)
        widget_obj.setVisible(bool(visible) and self._extra_top_right_extensions_visible)
        return widget_obj

    def set_top_right_extensions_visible(self, visible: bool) -> None:
        """统一切换右上角扩展控件可见性（Host 借还共享画布时使用）。"""
        self._extra_top_right_extensions_visible = bool(visible)
        TopRightControlsManager.set_extension_widgets_visible(self, bool(visible))

    # === 画布内搜索（Ctrl+F） ===

    def open_search_overlay(self) -> None:
        """打开并聚焦画布内搜索浮层（不依赖场景实现，缺少模型时仅展示输入框）。"""
        if hasattr(self, "search_overlay") and self.search_overlay:
            self.search_overlay.open_and_focus()

    # === 加载遮罩（大图加载/自动排版） ===

    def show_loading_overlay(
        self,
        *,
        title: str,
        detail: str = "",
        progress_value: int | None = None,
        progress_max: int | None = None,
    ) -> None:
        overlay = getattr(self, "loading_overlay", None)
        if overlay is None:
            return
        overlay.show_loading(
            title=str(title or "正在处理…"),
            detail=str(detail or ""),
            progress_value=progress_value,
            progress_max=progress_max,
            cancelable=False,
            on_cancel=None,
        )

    def update_loading_overlay_progress(self, *, progress_value: int | None, progress_max: int | None) -> None:
        overlay = getattr(self, "loading_overlay", None)
        if overlay is None:
            return
        overlay.set_progress(progress_value=progress_value, progress_max=progress_max)

    def update_loading_overlay_detail(self, detail: str) -> None:
        overlay = getattr(self, "loading_overlay", None)
        if overlay is None:
            return
        overlay.set_detail_text(str(detail or ""))

    def hide_loading_overlay(self) -> None:
        overlay = getattr(self, "loading_overlay", None)
        if overlay is None:
            return
        overlay.hide_loading()

    # === 自动排版（委托给 AutoLayoutController） ===

    def _on_auto_layout_clicked(self) -> None:
        """自动排版按钮点击事件 - 委托给自动排版控制器"""
        AutoLayoutController.run(self)

    # === EditSessionCapabilities（单一真源） ===

    @property
    def edit_session_capabilities(self) -> EditSessionCapabilities:
        return self._edit_session_capabilities

    def set_edit_session_capabilities(self, capabilities: EditSessionCapabilities) -> None:
        """更新会话能力，并同步 read_only 到视图与当前场景。"""
        self._edit_session_capabilities = capabilities
        self._read_only = bool(capabilities.is_read_only)

        # 自动排版按钮：仅在“允许交互 + 允许校验”的会话中开放。
        # 说明：
        # - 自动排版入口依赖校验能力（can_validate=True），因为排版前必须做图验证；
        # - 是否允许交互（can_interact）不应成为硬条件：例如复合节点库预览页保持只读，
        #   但允许自动排版来“整理视图”以便浏览结构（修改不落盘）。
        if hasattr(self, "auto_layout_button") and self.auto_layout_button:
            should_show_auto_layout = bool(capabilities.can_validate)
            self.auto_layout_button.setVisible(should_show_auto_layout)
            TopRightControlsManager.update_position(self)

        current_scene = self.scene()
        if current_scene is not None and hasattr(current_scene, "set_edit_session_capabilities"):
            current_scene.set_edit_session_capabilities(capabilities)

    @property
    def read_only(self) -> bool:
        """兼容字段：只读由 capabilities.can_interact 推导。"""
        return self._read_only

    @read_only.setter
    def read_only(self, value: bool) -> None:
        # 兼容旧写法：只改“可交互”能力，保留其余能力位。
        self.set_edit_session_capabilities(
            self._edit_session_capabilities.with_overrides(can_interact=not bool(value))
        )


