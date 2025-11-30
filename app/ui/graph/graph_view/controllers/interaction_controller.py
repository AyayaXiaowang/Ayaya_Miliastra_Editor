"""图视图交互控制器

负责处理所有键盘鼠标事件、交互状态管理、帧设置优化等。

拖拽模式说明：
- 默认使用 NoDrag 模式
- 左键按下时动态判断：
  * 点击节点/端口 → NoDrag 模式，允许拖拽节点或创建连线
  * 点击空白处 → RubberBandDrag 模式，允许框选多个节点
- 右键/中键/空格+左键时切换为 ScrollHandDrag 实现画布平移
- 释放后恢复为 NoDrag 模式
"""
from __future__ import annotations

import time

from typing import TYPE_CHECKING, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from ui.graph.graph_view import GraphView


class GraphViewInteractionController:
    """图视图交互控制器
    
    管理所有输入事件处理与交互期间的帧设置优化。
    """
    
    def __init__(self, view: "GraphView"):
        self.view = view
        # 交互状态
        self._panning = False
        self._space_down = False
        self._last_left_press_pos: Optional[QtCore.QPoint] = None
        self._right_button_pressed_pos: Optional[QtCore.QPoint] = None
        # 左键交互期间（拖拽节点/框选/端口连线预览）临时提升更新模式的开关与保存值
        self._interaction_elevated: bool = False
        self._saved_cache_mode_interaction: Optional[QtWidgets.QGraphicsView.CacheMode] = None
        self._saved_update_mode_interaction: Optional[QtWidgets.QGraphicsView.ViewportUpdateMode] = None
        # 拖拽期间的缓存/更新模式保存
        self._saved_cache_mode: Optional[QtWidgets.QGraphicsView.CacheMode] = None
        self._saved_update_mode: Optional[QtWidgets.QGraphicsView.ViewportUpdateMode] = None
        # 拖拽期间的渲染提示保存（用于临时关闭高成本抗锯齿选项，减轻大图平移时的重绘开销）
        self._saved_render_hints_pan: Optional[QtGui.QPainter.RenderHints] = None
        self._last_pan_followup_ts: float = 0.0
    
    def handle_wheel(self, event: QtGui.QWheelEvent) -> bool:
        """处理滚轮事件（缩放）
        
        Returns:
            True 表示事件已处理
        """
        # 若光标位于前景弹出卡片（如"布局Y坐标调试"Tooltip）之上，则将滚轮事件派发给该卡片，避免影响下方节点图
        scene = self.view.scene()
        if scene and hasattr(scene, "_ydebug_tooltip_widget"):
            tooltip = getattr(scene, "_ydebug_tooltip_widget", None)
            if tooltip is not None and tooltip.isVisible():
                local_pt_viewport = event.position().toPoint()
                # Tooltip 以 viewport 为父级，几何坐标与本地事件坐标一致
                if tooltip.geometry().contains(local_pt_viewport):
                    # 将事件重定向到 Tooltip（或其子控件，例如 QScrollArea），即便没有滚动条也不再触发画布缩放/滚动
                    local_pt_tooltip = tooltip.mapFrom(self.view.viewport(), local_pt_viewport)
                    target_widget: QtWidgets.QWidget = tooltip.childAt(local_pt_tooltip)
                    if target_widget is None:
                        target_widget = tooltip
                    global_pt_tooltip = target_widget.mapToGlobal(target_widget.mapFrom(tooltip, local_pt_tooltip))
                    redirected_event = QtGui.QWheelEvent(
                        QtCore.QPointF(target_widget.mapFromGlobal(global_pt_tooltip)),
                        QtCore.QPointF(global_pt_tooltip),
                        event.pixelDelta(),
                        event.angleDelta(),
                        event.buttons(),
                        event.modifiers(),
                        event.phase(),
                        event.inverted(),
                        event.source(),
                    )
                    QtWidgets.QApplication.sendEvent(target_widget, redirected_event)
                    event.accept()
                    return True
        
        from ui.foundation.interaction_helpers import handle_wheel_zoom_for_view
        handle_wheel_zoom_for_view(self.view, event, base_factor_per_step=1.15, min_scale=0.02, max_scale=5.0)
        # 失效背景层以保持网格与缩放后一致
        self.invalidate_background()
        # 触发重绘以更新坐标显示
        self.view.viewport().update()
        # 更新小地图
        if self.view.mini_map:
            self.view.mini_map.update_viewport_rect()
        # 更新节点详情浮窗位置（如果正在显示）
        if self.view.overlay_manager:
            self.view.overlay_manager.request_position_update()
        self._sync_ydebug_tooltip_position()
        return True
    
    def handle_mouse_press(self, event: QtGui.QMouseEvent) -> bool:
        """处理鼠标按下事件
        
        Returns:
            True 表示事件已处理并应拦截
        """
        # 优先拦截：布局Y调试'！'图标点击与空白关闭（避免被节点项吃掉事件）
        from engine.configs.settings import settings as _settings_ydebug
        if getattr(_settings_ydebug, "SHOW_LAYOUT_Y_DEBUG", False):
            scene = self.view.scene()
            if scene:
                scene_pos = self.view.mapToScene(event.pos())
                icon_map = getattr(scene, "_ydebug_icon_rects", {}) or {}
                # 命中图标则打开/刷新Tooltip并吃掉事件
                hit_node_id = None
                hit_reason = ""
                for _nid, _rect in icon_map.items():
                    if _rect.contains(scene_pos):
                        hit_node_id = _nid
                        hit_reason = "rect"
                        break
                    # 扩展命中区域 ±6 提升可点性
                    expanded = _rect.adjusted(-6.0, -6.0, 6.0, 6.0)
                    if expanded.contains(scene_pos):
                        hit_node_id = _nid
                        hit_reason = "expanded"
                        break
                if hit_node_id:
                    node_item = scene.get_node_item(hit_node_id)
                    if node_item:
                        node_rect = node_item.sceneBoundingRect()
                        # 改为图标位于右上角后，Tooltip 锚点也随之调整为靠右
                        anchor = QtCore.QPointF(float(node_rect.right()) - 3.0, float(node_rect.top()) + 3.0)
                    else:
                        anchor = scene_pos
                    scene._open_ydebug_tooltip(hit_node_id, anchor)
                    return True  # 拦截事件
                else:
                    # 计算回退命中：基于当前节点矩形推导图标矩形（仅对有调试数据的节点）
                    debug_map = getattr(scene.model, "_layout_y_debug_info", {}) or {}
                    fallback_hit_id = None
                    for _nid, _item in scene.node_items.items():
                        if _nid not in debug_map:
                            continue
                        rect = scene._get_ydebug_icon_rect_for_item(_item)
                        expanded = rect.adjusted(-8.0, -8.0, 8.0, 8.0)
                        if expanded.contains(scene_pos):
                            fallback_hit_id = _nid
                            break
                    if fallback_hit_id:
                        node_item = scene.get_node_item(fallback_hit_id)
                        if node_item:
                            node_rect = node_item.sceneBoundingRect()
                            anchor = QtCore.QPointF(float(node_rect.right()) - 3.0, float(node_rect.top()) + 3.0)
                        else:
                            anchor = scene_pos
                        scene._open_ydebug_tooltip(fallback_hit_id, anchor)
                        return True  # 拦截事件
                    # 辅助调试：打印最近图标中心与距离
                    nearest_id = None
                    nearest_dist = 1e9
                    nearest_cx = 0.0
                    nearest_cy = 0.0
                    for _nid, _rect in icon_map.items():
                        cx = float(_rect.center().x())
                        cy = float(_rect.center().y())
                        dx = float(scene_pos.x()) - cx
                        dy = float(scene_pos.y()) - cy
                        d2 = dx * dx + dy * dy
                        if d2 < nearest_dist:
                            nearest_dist = d2
                            nearest_id = _nid
                            nearest_cx = cx
                            nearest_cy = cy
                # 未命中图标：保留已有 Tooltip，不再因点击空白处自动关闭
        
        # 右键/中键/空格+左键：启动拖拽平移
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            # 记录右键按下的位置，用于判断是否有拖动（使用QPoint以便与contextMenuEvent的event.pos()类型一致）
            self._right_button_pressed_pos = event.pos()
            self.view.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
            self._panning = True
            self.begin_pan_frame_settings()
            return True  # 已处理，需要伪造左键事件
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self.view.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
            self._panning = True
            self.begin_pan_frame_settings()
            return True  # 已处理，需要伪造左键事件
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._space_down:
            self.view.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
            self._panning = True
            self.begin_pan_frame_settings()
            return True  # 已处理，需要伪造左键事件
        
        # 左键普通交互（节点拖拽/框选/端口连线预览）：根据命中类型决定是否临时提升更新模式
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # 记录按下位置，用于后续判断是否为“点击”而非拖拽
            self._last_left_press_pos = event.pos()
            # 动态设置拖拽模式：点击空白处启用框选，点击节点/端口时允许拖拽
            scene_pos = self.view.mapToScene(event.pos())
            item = self.view.scene().itemAt(scene_pos, QtGui.QTransform()) if self.view.scene() else None
            
            # 导入需要在运行时进行
            from ui.graph.items.node_item import NodeGraphicsItem
            from ui.graph.items.port_item import PortGraphicsItem
            
            # 点击到节点或端口：使用 NoDrag 允许拖拽节点/连线
            hit_node_or_port = isinstance(item, (NodeGraphicsItem, PortGraphicsItem)) or (
                item and item.parentItem() and isinstance(item.parentItem(), (NodeGraphicsItem, PortGraphicsItem))
            )
            if hit_node_or_port:
                self.view.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
                self.begin_interaction_frame_settings()
            else:
                # 点击空白处：启用框选
                self.view.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        
        return False  # 未拦截，继续传递
    
    def handle_mouse_release(self, event: QtGui.QMouseEvent) -> bool:
        """处理鼠标释放事件
        
        Returns:
            True 表示事件已处理并应拦截
        """
        if self._panning:
            # 恢复为 NoDrag（默认状态，左键按下时会动态判断）
            self.view.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
            self._panning = False
            self.end_pan_frame_settings()
            # 释放后失效一次背景，矫正网格
            self.invalidate_background()
            # 触发重绘以更新坐标显示
            self.view.viewport().update()
            return True  # 已处理，需要伪造左键释放
        
        # 普通左键交互结束时恢复更新模式
        if self._interaction_elevated:
            self.end_interaction_frame_settings()

        # 只读预览场景下，根据单击位置发出“图元素点击/空白点击”信号，供上层联动任务清单。
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and getattr(self.view, "enable_click_signals", False)
            and getattr(self.view, "read_only", False)
        ):
            press_pos = self._last_left_press_pos
            self._last_left_press_pos = None
            if press_pos is not None:
                distance = (event.pos() - press_pos).manhattanLength()
                # 小于等于 4 像素视为点击，避免拖拽也触发
                if distance <= 4:
                    scene = self.view.scene()
                    if scene is not None:
                        scene_pos = self.view.mapToScene(event.pos())
                        item = scene.itemAt(scene_pos, QtGui.QTransform())

                        from ui.graph.graph_scene import NodeGraphicsItem, EdgeGraphicsItem

                        if isinstance(item, NodeGraphicsItem):
                            node_id = getattr(item.node, "id", "")
                            node_title = getattr(item.node, "title", "")
                            payload = {
                                "type": "node",
                                "node_id": node_id,
                                "node_title": node_title,
                            }
                            self.view.graph_element_clicked.emit(payload)
                        elif isinstance(item, EdgeGraphicsItem):
                            edge_id = item.edge_id
                            edge = scene.model.edges.get(edge_id) if hasattr(scene, "model") else None
                            if edge is not None:
                                payload = {
                                    "type": "edge",
                                    "edge_id": edge_id,
                                    "src_node": edge.src_node,
                                    "dst_node": edge.dst_node,
                                }
                                self.view.graph_element_clicked.emit(payload)
                        else:
                            self.view.graph_element_clicked.emit({"type": "background"})

        return False  # 未拦截
    
    def handle_mouse_double_click(self, event: QtGui.QMouseEvent) -> bool:
        """处理双击事件
        
        Returns:
            True 表示事件已处理
        """
        from ui.graph.graph_scene import NodeGraphicsItem, EdgeGraphicsItem
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            scene_pos = self.view.mapToScene(event.pos())
            item = self.view.scene().itemAt(scene_pos, QtGui.QTransform())
            
            if isinstance(item, NodeGraphicsItem):
                # 检查是否是复合节点
                if item.node.category == "复合节点":
                    # 双击复合节点，发射跳转到复合节点页面的信号
                    jump_info = {
                        "type": "composite_node",
                        "node_id": item.node.id,
                        "node_title": item.node.title,
                        "composite_name": item.node.title  # 复合节点的名称
                    }
                    self.view.jump_to_graph_element.emit(jump_info)
                    return True
                
                # 只读模式下，双击普通节点发射跳转信号
                if self.view.read_only:
                    jump_info = {
                        "type": "node",
                        "node_id": item.node.id,
                        "node_title": item.node.title
                    }
                    self.view.jump_to_graph_element.emit(jump_info)
                    return True
            elif isinstance(item, EdgeGraphicsItem) and self.view.read_only:
                # 双击连线，发射跳转信号
                edge = self.view.scene().model.edges.get(item.edge_id)
                if edge:
                    jump_info = {
                        "type": "edge",
                        "edge_id": item.edge_id,
                        "src_node": edge.src_node,
                        "dst_node": edge.dst_node
                    }
                    self.view.jump_to_graph_element.emit(jump_info)
                return True
        
        return False  # 未处理
    
    def handle_key_press(self, event: QtGui.QKeyEvent) -> bool:
        """处理按键事件
        
        Returns:
            True 表示事件已处理
        """
        if event.key() == QtCore.Qt.Key.Key_Space:
            self._space_down = True
            return True
        elif event.key() == QtCore.Qt.Key.Key_Delete:
            # 只读模式下禁用删除
            if not self.view.read_only:
                # 删除选中的节点和连线
                if self.view.scene():
                    self.view.scene().delete_selected_items()
            return True
        elif event.key() == QtCore.Qt.Key.Key_Z and event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
            # 只读模式下禁用撤销
            if not self.view.read_only:
                # Ctrl+Z 撤销
                if self.view.scene():
                    self.view.scene().undo_manager.undo()
            return True
        elif event.key() == QtCore.Qt.Key.Key_Y and event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
            # 只读模式下禁用重做
            if not self.view.read_only:
                # Ctrl+Y 重做
                if self.view.scene():
                    self.view.scene().undo_manager.redo()
            return True
        elif event.key() == QtCore.Qt.Key.Key_C and event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
            # 只读模式下禁用复制
            if not self.view.read_only:
                # Ctrl+C 复制选中的节点
                if self.view.scene():
                    # 检查是否有文本编辑控件获得焦点
                    focus_item = self.view.scene().focusItem()
                    if isinstance(focus_item, QtWidgets.QGraphicsTextItem) and focus_item.textInteractionFlags():
                        # 有文本控件在编辑，不拦截，让文本控件处理复制
                        return False
                    # 否则执行节点复制
                    self.view.scene().copy_selected_nodes()
            return True
        elif event.key() == QtCore.Qt.Key.Key_V and event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
            # 只读模式下禁用粘贴
            if not self.view.read_only:
                # Ctrl+V 粘贴节点
                if self.view.scene():
                    self.view.scene().paste_nodes()
            return True
        
        return False  # 未处理
    
    def handle_key_release(self, event: QtGui.QKeyEvent) -> bool:
        """处理按键释放事件
        
        Returns:
            True 表示事件已处理
        """
        if event.key() == QtCore.Qt.Key.Key_Space:
            self._space_down = False
            return True
        return False
    
    def handle_scroll_contents(self, dx: int, dy: int) -> None:
        """滚动内容时触发更新"""
        # 非拖拽场景（例如程序性滚动），仍然主动失效背景以保证网格与坐标精确对齐
        # 画布平移过程中（ScrollHandDrag），则依赖 Qt 自身的滚动与缓存机制，仅在平移结束时统一失效一次背景，
        # 避免大图下每个像素位移都触发整视口背景重建。
        if not self._panning:
            self.invalidate_background()
            # 触发重绘以更新坐标显示
            self.view.viewport().update()
        run_followups = True
        if self._panning:
            run_followups = self._should_run_pan_followups()
        if self.view.mini_map and (run_followups or not self._panning):
            from ui.graph.graph_view.assembly.view_assembly import ViewAssembly
            ViewAssembly.update_mini_map_position(self.view)
            self.view.mini_map.raise_()
            self.view.mini_map.update_viewport_rect()
        if self.view.overlay_manager and (run_followups or not self._panning):
            self.view.overlay_manager.request_position_update()
        if run_followups or not self._panning:
            self._sync_ydebug_tooltip_position()
    
    def invalidate_background(self) -> None:
        """使当前视口对应的场景背景层失效并重建缓存，确保网格在拖拽/滚动/缩放后对齐。
        
        仅失效当前可见区域以降低重绘成本。
        """
        scene = self.view.scene()
        if not scene:
            return
        # 当前视口对应的场景矩形
        view_rect = self.view.viewport().rect()
        if view_rect.isNull():
            return
        scene_rect = self.view.mapToScene(view_rect).boundingRect()
        # 失效背景层（不影响前景与项）
        scene.invalidate(scene_rect, QtWidgets.QGraphicsScene.SceneLayer.BackgroundLayer)
        # 同时重置视图缓存内容，避免 CacheBackground 残留
        self.view.resetCachedContent()
    
    def begin_pan_frame_settings(self) -> None:
        """在开始画布拖拽时，暂时调整渲染提示以降低重绘成本。"""
        # 保存当前设置
        self._saved_cache_mode = self.view.cacheMode()
        self._saved_update_mode = self.view.viewportUpdateMode()
        self._saved_render_hints_pan = self.view.renderHints()
        # 性能：拖拽期间关闭抗锯齿与平滑像素缩放，降低大图重绘成本
        self.view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        self.view.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
        self.view.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, False)
    
    def end_pan_frame_settings(self) -> None:
        """结束画布拖拽后，恢复原有缓存与更新模式。"""
        # 恢复缓存与更新模式
        if self._saved_cache_mode is not None:
            self.view.setCacheMode(self._saved_cache_mode)
        if self._saved_update_mode is not None:
            self.view.setViewportUpdateMode(self._saved_update_mode)
        # 恢复拖拽前的渲染提示配置
        if self._saved_render_hints_pan is not None:
            self.view.setRenderHints(self._saved_render_hints_pan)
            self._saved_render_hints_pan = None
        # 清理一次缓存内容并请求重绘背景
        self.invalidate_background()
        self._run_pan_followups_immediately()
    
    def begin_interaction_frame_settings(self) -> None:
        """在左键交互（节点拖拽/框选/连线预览）期间，暂时关闭背景缓存并使用整视口更新，以避免残影。"""
        if self._interaction_elevated:
            return
        self._saved_cache_mode_interaction = self.view.cacheMode()
        self._saved_update_mode_interaction = self.view.viewportUpdateMode()
        self.view.setCacheMode(QtWidgets.QGraphicsView.CacheModeFlag.CacheNone)
        self.view.setViewportUpdateMode(QtWidgets.QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self._interaction_elevated = True
    
    def end_interaction_frame_settings(self) -> None:
        """结束左键交互后恢复原有缓存与更新模式。"""
        if not self._interaction_elevated:
            return
        if self._saved_cache_mode_interaction is not None:
            self.view.setCacheMode(self._saved_cache_mode_interaction)
        if self._saved_update_mode_interaction is not None:
            self.view.setViewportUpdateMode(self._saved_update_mode_interaction)
        self._interaction_elevated = False
        # 失效一次背景并请求整视口重绘，确保清理干净
        self.invalidate_background()
        self.view.viewport().update()
    
    @property
    def is_panning(self) -> bool:
        """是否正在拖拽平移"""
        return self._panning
    
    @property
    def right_button_pressed_pos(self) -> Optional[QtCore.QPoint]:
        """右键按下位置（用于判断是否为拖拽）"""
        return self._right_button_pressed_pos
    
    def clear_right_button_pressed_pos(self) -> None:
        """清除右键按下位置记录"""
        self._right_button_pressed_pos = None

    def _sync_ydebug_tooltip_position(self) -> None:
        scene = self.view.scene()
        if scene and hasattr(scene, "_reposition_ydebug_tooltip"):
            scene._reposition_ydebug_tooltip()

    def _current_pan_followup_interval(self) -> float:
        scale = self.view.transform().m11()
        if scale < 0.35:
            return 0.032
        if scale < 0.6:
            return 0.022
        return 0.016

    def _should_run_pan_followups(self) -> bool:
        interval = self._current_pan_followup_interval()
        now = time.perf_counter()
        if now - self._last_pan_followup_ts >= interval:
            self._last_pan_followup_ts = now
            return True
        return False

    def _run_pan_followups_immediately(self) -> None:
        if self.view.mini_map:
            from ui.graph.graph_view.assembly.view_assembly import ViewAssembly
            ViewAssembly.update_mini_map_position(self.view)
            self.view.mini_map.raise_()
            self.view.mini_map.update_viewport_rect()
        if self.view.overlay_manager:
            self.view.overlay_manager.request_position_update()
        self._sync_ydebug_tooltip_position()
        self._last_pan_followup_ts = 0.0

