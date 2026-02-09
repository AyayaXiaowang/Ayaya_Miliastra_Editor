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
    from app.ui.graph.graph_view import GraphView


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
        # 画布平移期间临时禁用 view.interactive，避免右键平移在“节点/连线之上”被图形项吃掉
        self._saved_interactive_pan: Optional[bool] = None
        self._last_pan_followup_ts: float = 0.0
        # 平移静态快照覆盖层（按需创建）
        self._pan_freeze_overlay = None
        self._pan_freeze_active: bool = False
        # 缩放静态快照：滚轮缩放期间冻结为静态快照（避免每步滚轮重绘 items）
        self._zoom_freeze_active: bool = False
        # 缩放冻结覆盖层（独立于 pan freeze），避免滚轮期间触发任何全场景渲染
        self._zoom_freeze_overlay = None
        self._zoom_freeze_base_scale: float = 1.0
        # 缩放冻结期间累计的“相对缩放因子”（相对于 begin_freeze 时的 view.scale），仅在滚轮结束时一次性应用到 view
        self._zoom_freeze_pending_factor: float = 1.0
        self._zoom_freeze_last_pivot: QtCore.QPointF | None = None
        # 滚轮缩放交互的 debounce timer（用于“滚轮停止后”统一收尾）
        self._wheel_zoom_debounce_timer: QtCore.QTimer | None = None
        self._saved_update_mode_zoom: Optional[QtWidgets.QGraphicsView.ViewportUpdateMode] = None
    
    def handle_wheel(self, event: QtGui.QWheelEvent) -> bool:
        """处理滚轮事件（缩放）
        
        Returns:
            True 表示事件已处理
        """
        # 若光标位于前景弹出卡片（如"布局Y坐标调试"感叹号详情）之上，
        # 则将滚轮事件派发给该卡片（或其子控件，如 QScrollArea），避免影响下方节点图缩放。
        scene = self.view.scene()
        tooltip = None
        if scene is not None:
            # 新实现：YDebugInteractionMixin 通过 _ydebug_tooltip_overlay 持有卡片 widget
            overlay = getattr(scene, "_ydebug_tooltip_overlay", None)
            tooltip = getattr(overlay, "_widget", None) if overlay is not None else None
            # 兼容旧字段（若存在）
            if tooltip is None:
                tooltip = getattr(scene, "_ydebug_tooltip_widget", None)

        if tooltip is not None and hasattr(tooltip, "isVisible") and tooltip.isVisible():
            local_pt_viewport = event.position().toPoint()
            # Tooltip 以 viewport 为父级，几何坐标与本地事件坐标一致
            if tooltip.geometry().contains(local_pt_viewport):
                local_pt_tooltip = tooltip.mapFrom(self.view.viewport(), local_pt_viewport)
                target_widget: QtWidgets.QWidget | None = tooltip.childAt(local_pt_tooltip)
                if target_widget is None:
                    target_widget = tooltip
                global_pos = self.view.viewport().mapToGlobal(local_pt_viewport)
                local_pos_target = target_widget.mapFromGlobal(global_pos)
                redirected_event = QtGui.QWheelEvent(
                    QtCore.QPointF(local_pos_target),
                    QtCore.QPointF(global_pos),
                    event.pixelDelta(),
                    event.angleDelta(),
                    event.buttons(),
                    event.modifiers(),
                    event.phase(),
                    event.inverted(),
                )
                QtWidgets.QApplication.sendEvent(target_widget, redirected_event)
                event.accept()
                return True
        
        from engine.configs.settings import settings as _settings
        zoom_freeze_enabled = bool(getattr(_settings, "GRAPH_ZOOM_FREEZE_VIEWPORT_ENABLED", False))
        # 滚轮缩放：同步“交互中”状态（用于隐藏端口/叠层降级、跳过网格等优化）。
        self._begin_wheel_zoom_interaction(event)
        if zoom_freeze_enabled:
            self._begin_zoom_freeze(event)

        if zoom_freeze_enabled and bool(getattr(self, "_zoom_freeze_active", False)):
            # 缩放冻结：为保证“过程丝滑”，滚轮期间不对 QGraphicsView 做 scale，
            # 仅更新覆盖层的预览变换；最终缩放在 debounce 结束时一次性应用到 view。
            angle = int(event.angleDelta().y())
            pixel = int(event.pixelDelta().y())
            steps = float(angle) / 120.0 if angle != 0 else (float(pixel) / 120.0 if pixel != 0 else 0.0)
            if steps != 0.0:
                base_factor_per_step = 1.15
                min_scale = 0.02
                max_scale = 5.0

                base_scale = float(getattr(self, "_zoom_freeze_base_scale", 1.0) or 1.0)
                if base_scale <= 0.0:
                    base_scale = 1.0

                if steps > 0:
                    event_factor = float(base_factor_per_step) ** float(steps)
                else:
                    event_factor = (1.0 / float(base_factor_per_step)) ** abs(float(steps))

                pending = float(getattr(self, "_zoom_freeze_pending_factor", 1.0) or 1.0)
                pending *= float(event_factor)

                # clamp：以最终 view.scale 为口径约束（避免预览走到非法倍率）
                target_scale = float(base_scale) * float(pending)
                if target_scale < float(min_scale):
                    pending = float(min_scale) / float(base_scale)
                elif target_scale > float(max_scale):
                    pending = float(max_scale) / float(base_scale)

                self._zoom_freeze_pending_factor = float(pending)
                pivot = QtCore.QPointF(float(event.position().x()), float(event.position().y()))
                self._zoom_freeze_last_pivot = pivot

                overlay = getattr(self, "_zoom_freeze_overlay", None)
                set_zoom = getattr(overlay, "set_zoom_transform", None) if overlay is not None else None
                if callable(set_zoom):
                    set_zoom(float(pending), pivot=pivot)

            event.accept()
            # 缩放冻结期间：不做背景失效/小地图/浮窗联动，统一在 debounce 结束时补齐一次。
            return True

        # 非冻结：常规缩放（会直接对 view.scale）
        from app.ui.foundation.interaction_helpers import handle_wheel_zoom_for_view

        handle_wheel_zoom_for_view(self.view, event, base_factor_per_step=1.15, min_scale=0.02, max_scale=5.0)

        # 常规缩放：立即同步背景与叠层
        self.invalidate_background()
        self.view.viewport().update()
        if self.view.mini_map:
            self.view.mini_map.update_viewport_rect()
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
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and getattr(_settings_ydebug, "SHOW_LAYOUT_Y_DEBUG", False)
        ):
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
        
        # 左键普通交互（节点拖拽/框选/端口连线预览）：根据命中类型动态切换拖拽模式，并在交互期间统一提升更新模式
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # 记录按下位置，用于后续判断是否为“点击”而非拖拽
            self._last_left_press_pos = event.pos()
            # 动态设置拖拽模式：点击空白处启用框选，点击节点/端口时允许拖拽
            scene_pos = self.view.mapToScene(event.pos())
            scene = self.view.scene()
            item = scene.itemAt(scene_pos, QtGui.QTransform()) if scene else None
            
            # 导入需要在运行时进行
            from app.ui.graph.items.node_item import NodeGraphicsItem
            from app.ui.graph.items.port_item import PortGraphicsItem
            from app.ui.graph.items.edge_item import EdgeGraphicsItem
            from app.ui.graph.items.fast_preview_items import FastPreviewEdgeGraphicsItem
            
            # 点击到节点或端口：使用 NoDrag 允许拖拽节点/连线
            hit_node_or_port = isinstance(
                item,
                (
                    NodeGraphicsItem,
                    PortGraphicsItem,
                    EdgeGraphicsItem,
                    FastPreviewEdgeGraphicsItem,
                ),
            ) or (
                item and item.parentItem() and isinstance(item.parentItem(), (NodeGraphicsItem, PortGraphicsItem))
            )
            # 批量渲染边（无 per-edge item）时，点击连线也应视为“命中图元素”，避免误进入 RubberBand 框选
            if not hit_node_or_port and scene is not None:
                has_batched = getattr(scene, "has_batched_fast_preview_edges", None)
                pick_batched = getattr(scene, "pick_batched_edge_id_at", None)
                if callable(has_batched) and has_batched() and callable(pick_batched):
                    if pick_batched(scene_pos) is not None:
                        hit_node_or_port = True
            if hit_node_or_port:
                self.view.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
            else:
                # 点击空白处：启用框选
                self.view.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
            # 对所有左键交互（包括节点拖拽与框选）启用高刷新模式，避免残影
            self.begin_interaction_frame_settings()
        
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

                        from app.ui.graph.items.node_item import NodeGraphicsItem
                        from app.ui.graph.items.edge_item import EdgeGraphicsItem
                        from app.ui.graph.items.fast_preview_items import FastPreviewEdgeGraphicsItem

                        if isinstance(item, NodeGraphicsItem):
                            node_id = getattr(item.node, "id", "")
                            node_title = getattr(item.node, "title", "")
                            payload = {
                                "type": "node",
                                "node_id": node_id,
                                "node_title": node_title,
                            }
                            self.view.graph_element_clicked.emit(payload)
                        elif isinstance(item, (EdgeGraphicsItem, FastPreviewEdgeGraphicsItem)):
                            edge_id = getattr(item, "edge_id", "")
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
                            # 批量渲染边：itemAt 命中不到连线，需要走模型级命中
                            edge_id = None
                            pick_batched = getattr(scene, "pick_batched_edge_id_at", None)
                            if callable(pick_batched):
                                edge_id = pick_batched(scene_pos)
                            if edge_id is None:
                                self.view.graph_element_clicked.emit({"type": "background"})
                                return False
                            edge = scene.model.edges.get(edge_id) if hasattr(scene, "model") else None
                            if edge is None:
                                self.view.graph_element_clicked.emit({"type": "background"})
                                return False
                            payload = {
                                "type": "edge",
                                "edge_id": edge_id,
                                "src_node": edge.src_node,
                                "dst_node": edge.dst_node,
                            }
                            self.view.graph_element_clicked.emit(payload)

        return False  # 未拦截
    
    def handle_mouse_double_click(self, event: QtGui.QMouseEvent) -> bool:
        """处理双击事件
        
        Returns:
            True 表示事件已处理
        """
        from app.ui.graph.items.node_item import NodeGraphicsItem
        from app.ui.graph.items.edge_item import EdgeGraphicsItem
        from app.ui.graph.items.fast_preview_items import FastPreviewEdgeGraphicsItem
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            scene_pos = self.view.mapToScene(event.pos())
            item = self.view.scene().itemAt(scene_pos, QtGui.QTransform())
            
            if isinstance(item, NodeGraphicsItem):
                node_model = getattr(item, "node", None)
                node_id = str(getattr(node_model, "id", "") or "")
                node_title = str(getattr(node_model, "title", "") or "")
                composite_id = str(getattr(node_model, "composite_id", "") or "").strip()
                node_category = str(getattr(node_model, "category", "") or "").strip()
                # 复合节点识别：
                # - 首选 composite_id（稳定标识符，避免改名后无法定位）
                # - 兼容旧数据/旧库：仍允许通过 category 识别
                is_composite_node = bool(composite_id) or node_category in ("复合节点", "复合")
                if is_composite_node:
                    jump_info = {
                        "type": "composite_node",
                        "node_id": node_id,
                        "node_title": node_title,
                        "composite_id": composite_id,
                        "composite_name": node_title,
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
            elif isinstance(item, (EdgeGraphicsItem, FastPreviewEdgeGraphicsItem)) and self.view.read_only:
                # 双击连线，发射跳转信号
                edge_id = getattr(item, "edge_id", "")
                edge = self.view.scene().model.edges.get(edge_id)
                if edge:
                    jump_info = {
                        "type": "edge",
                        "edge_id": edge_id,
                        "src_node": edge.src_node,
                        "dst_node": edge.dst_node
                    }
                    self.view.jump_to_graph_element.emit(jump_info)
                return True
            elif self.view.read_only:
                # 批量渲染边：itemAt 命中不到连线，需要走模型级命中
                scene = self.view.scene()
                if scene is None:
                    return False
                edge_id = None
                pick_batched = getattr(scene, "pick_batched_edge_id_at", None)
                if callable(pick_batched):
                    edge_id = pick_batched(scene_pos)
                if edge_id is None:
                    return False
                edge = scene.model.edges.get(edge_id) if hasattr(scene, "model") else None
                if edge is None:
                    return False
                jump_info = {
                    "type": "edge",
                    "edge_id": edge_id,
                    "src_node": edge.src_node,
                    "dst_node": edge.dst_node,
                }
                self.view.jump_to_graph_element.emit(jump_info)
                return True
        
        return False  # 未处理
    
    def handle_key_press(self, event: QtGui.QKeyEvent) -> bool:
        """处理按键事件
        
        Returns:
            True 表示事件已处理
        """
        # 关键：当焦点在“文本输入/文本编辑控件”上时，不应该拦截任何图级快捷键，
        # 否则会导致 Ctrl+C/Ctrl+V/Undo/Redo/Delete/Space 等被吞掉，用户无法在输入框内复制或编辑文本。
        #
        # 说明：
        # - QGraphicsTextItem（如节点端口的常量文本编辑框）是 Scene 的 focusItem，但 View 仍是 focusWidget；
        #   因此需要同时检查 scene.focusItem() 与 QApplication.focusWidget()。
        if self._has_focused_text_input():
            return False

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
            # 只读模式下禁用“节点复制”（文本复制由 _has_focused_text_input 提前放行）
            if not self.view.read_only:
                # Ctrl+C 复制选中的节点
                if self.view.scene():
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

    @staticmethod
    def _is_text_input_widget(widget: Optional[QtWidgets.QWidget]) -> bool:
        if widget is None:
            return False
        if isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QAbstractSpinBox)):
            return True
        if isinstance(widget, QtWidgets.QComboBox) and widget.isEditable():
            return True
        return False

    def _has_focused_text_input(self) -> bool:
        """判断当前是否有文本输入/编辑控件获得焦点。

        目的：当用户正在编辑/选择文本时，图级快捷键不要抢占键盘事件。
        """
        scene = self.view.scene()
        if scene is None:
            return False

        focused_scene_item = scene.focusItem()
        if isinstance(focused_scene_item, QtWidgets.QGraphicsTextItem):
            interaction_flags = focused_scene_item.textInteractionFlags()
            if interaction_flags != QtCore.Qt.TextInteractionFlag.NoTextInteraction:
                return True

        focused_widget = QtWidgets.QApplication.focusWidget()
        if self._is_text_input_widget(focused_widget):
            return True

        if isinstance(focused_scene_item, QtWidgets.QGraphicsProxyWidget):
            embedded_widget = focused_scene_item.widget()
            if self._is_text_input_widget(embedded_widget):
                return True
            if embedded_widget is not None and focused_widget is not None and embedded_widget.isAncestorOf(focused_widget):
                # 代理控件中的子控件（例如 QLineEdit）获得焦点
                return True

        return False
    
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
        monitor = None
        if bool(getattr(self.view, "_perf_panel_enabled", False)):
            monitor = getattr(self.view, "_perf_monitor", None)
        t_total0 = time.perf_counter() if monitor is not None else 0.0

        # 静态快照覆盖层：滚动时只移动覆盖层，不触发场景重绘（视图可能处于 NoViewportUpdate）。
        if (self._panning and bool(getattr(self, "_pan_freeze_active", False))) or bool(
            getattr(self, "_zoom_freeze_active", False)
        ):
            overlay = (
                getattr(self, "_pan_freeze_overlay", None)
                if (self._panning and bool(getattr(self, "_pan_freeze_active", False)))
                else getattr(self, "_zoom_freeze_overlay", None)
            )
            scroll_by = getattr(overlay, "scroll_by", None) if overlay is not None else None
            if callable(scroll_by):
                scroll_by(int(dx), int(dy))
            # 缩放冻结期间：跳过背景失效/小地图/浮窗联动，统一由 _end_zoom_freeze() 补齐一次。
            if bool(getattr(self, "_zoom_freeze_active", False)):
                if monitor is not None:
                    monitor.record_ms(
                        "controller.scrollContentsBy.total",
                        (time.perf_counter() - float(t_total0)) * 1000.0,
                    )
                return

        # 非拖拽场景（例如程序性滚动），仍然主动失效背景以保证网格与坐标精确对齐
        # 画布平移过程中（ScrollHandDrag），则依赖 Qt 自身的滚动与缓存机制，仅在平移结束时统一失效一次背景，
        # 避免大图下每个像素位移都触发整视口背景重建。
        if not self._panning:
            if monitor is not None:
                with monitor.scope("controller.scroll.invalidate_background"):
                    self.invalidate_background()
                    # 触发重绘以更新坐标显示
                    self.view.viewport().update()
            else:
                self.invalidate_background()
                # 触发重绘以更新坐标显示
                self.view.viewport().update()
        run_followups = True
        if self._panning:
            run_followups = self._should_run_pan_followups()
        if self.view.mini_map and (run_followups or not self._panning):
            from app.ui.graph.graph_view.assembly.view_assembly import ViewAssembly
            if monitor is not None:
                with monitor.scope("controller.scroll.minimap_followup"):
                    ViewAssembly.update_mini_map_position(self.view)
                    self.view.mini_map.raise_()
                    self.view.mini_map.update_viewport_rect()
            else:
                ViewAssembly.update_mini_map_position(self.view)
                self.view.mini_map.raise_()
                self.view.mini_map.update_viewport_rect()
        if self.view.overlay_manager and (run_followups or not self._panning):
            if monitor is not None:
                with monitor.scope("controller.scroll.overlay_followup"):
                    self.view.overlay_manager.request_position_update()
            else:
                self.view.overlay_manager.request_position_update()
        if run_followups or not self._panning:
            if monitor is not None:
                with monitor.scope("controller.scroll.ydebug_followup"):
                    self._sync_ydebug_tooltip_position()
            else:
                self._sync_ydebug_tooltip_position()

        if monitor is not None:
            monitor.record_ms(
                "controller.scrollContentsBy.total",
                (time.perf_counter() - float(t_total0)) * 1000.0,
            )
    
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

    def _ensure_wheel_zoom_debounce_timer(self) -> QtCore.QTimer:
        timer = getattr(self, "_wheel_zoom_debounce_timer", None)
        if isinstance(timer, QtCore.QTimer):
            return timer
        timer = QtCore.QTimer(self.view)
        timer.setSingleShot(True)
        timer.timeout.connect(self._end_wheel_zoom_interaction)
        self._wheel_zoom_debounce_timer = timer
        return timer
    
    def _begin_wheel_zoom_interaction(self, event: QtGui.QWheelEvent) -> None:
        """滚轮缩放交互开始/持续：标记场景状态并刷新 debounce。"""
        if event is None:
            return
        # 无增量：不触发（避免触控板的“空事件”延长交互态）
        if event.angleDelta().y() == 0 and event.pixelDelta().y() == 0:
            return
        # 拖拽平移期间不叠加滚轮缩放交互态，避免恢复逻辑打架
        if bool(getattr(self, "_panning", False)):
            return

        scene = self.view.scene()
        set_zooming = getattr(scene, "set_view_zooming", None) if scene is not None else None
        if callable(set_zooming):
            set_zooming(True)

        timer = self._ensure_wheel_zoom_debounce_timer()
        timer.start(140)
    
    def _cancel_wheel_zoom_interaction(self) -> None:
        """取消滚轮缩放交互态（用于进入拖拽平移等更高优先级交互时）。"""
        timer = getattr(self, "_wheel_zoom_debounce_timer", None)
        if isinstance(timer, QtCore.QTimer):
            timer.stop()
        scene = self.view.scene()
        set_zooming = getattr(scene, "set_view_zooming", None) if scene is not None else None
        if callable(set_zooming):
            set_zooming(False)
    
    def _end_wheel_zoom_interaction(self) -> None:
        """滚轮停止后收尾：恢复场景交互态与（若启用）缩放静态快照。"""
        scene = self.view.scene()
        if scene is not None:
            # 缩放结束：先同步 scale_hint，避免 LOD/命中测试口径滞后一帧。
            current_scale = float(self.view.transform().m11())
            set_hint = getattr(scene, "set_view_scale_hint", None)
            if callable(set_hint):
                set_hint(current_scale)
            else:
                setattr(scene, "view_scale_hint", current_scale)

            set_zooming = getattr(scene, "set_view_zooming", None)
            if callable(set_zooming):
                set_zooming(False)

        # 静态快照覆盖层：结束后内部会补齐一次背景/叠层联动刷新
        if bool(getattr(self, "_zoom_freeze_active", False)):
            self._end_zoom_freeze()
            return

        # 非静态快照：补一次背景失效，确保网格/叠层从低细节模式恢复
        self.invalidate_background()
        self.view.viewport().update()

    def _begin_zoom_freeze(self, event: QtGui.QWheelEvent) -> None:
        """滚轮缩放期间启用静态快照覆盖层（极致性能）。"""
        if event is None:
            return
        # 无增量：不触发冻结，避免触控板的“空事件”导致闪一下
        if event.angleDelta().y() == 0 and event.pixelDelta().y() == 0:
            return
        # 平移手抓期间不叠加缩放冻结，避免与 pan freeze 状态打架
        if bool(getattr(self, "_panning", False)):
            return

        monitor = None
        if bool(getattr(self.view, "_perf_panel_enabled", False)):
            monitor = getattr(self.view, "_perf_monitor", None)

        if not bool(getattr(self, "_zoom_freeze_active", False)):
            self._saved_update_mode_zoom = self.view.viewportUpdateMode()

            overlay = getattr(self, "_zoom_freeze_overlay", None)
            if overlay is None:
                from app.ui.graph.graph_view.overlays.zoom_freeze_overlay import ZoomFreezeOverlay

                overlay = ZoomFreezeOverlay(self.view)
                self._zoom_freeze_overlay = overlay

            t0 = time.perf_counter() if monitor is not None else 0.0
            begin = getattr(overlay, "begin_freeze", None)
            if callable(begin):
                begin()
                self._zoom_freeze_active = True
                self._zoom_freeze_base_scale = float(self.view.transform().m11() or 1.0)
                self._zoom_freeze_pending_factor = 1.0
                self._zoom_freeze_last_pivot = QtCore.QPointF(float(event.position().x()), float(event.position().y()))
                # 覆盖层必须在 viewport 之上（否则看起来“没静态”）
                if hasattr(overlay, "raise_"):
                    overlay.raise_()
                # 禁用视图更新：缩放过程中不重绘场景（覆盖层负责显示）
                self.view.setViewportUpdateMode(QtWidgets.QGraphicsView.ViewportUpdateMode.NoViewportUpdate)

                # 置顶：保持右上角控件/小地图在覆盖层之上
                try_raise = getattr(self.view, "mini_map", None)
                if try_raise is not None and hasattr(try_raise, "raise_"):
                    try_raise.raise_()
                from app.ui.graph.graph_view.top_right.controls_manager import TopRightControlsManager

                TopRightControlsManager.raise_all(self.view)
                perf_overlay = getattr(self.view, "_perf_overlay", None)
                if perf_overlay is not None and hasattr(perf_overlay, "raise_") and perf_overlay.isVisible():
                    perf_overlay.raise_()
                search_overlay = getattr(self.view, "search_overlay", None)
                if search_overlay is not None and hasattr(search_overlay, "raise_") and search_overlay.isVisible():
                    search_overlay.raise_()
                if monitor is not None:
                    monitor.record_ms(
                        "controller.zoom_freeze.capture",
                        (time.perf_counter() - float(t0)) * 1000.0,
                    )

    def _end_zoom_freeze(self) -> None:
        """结束缩放静态快照，恢复真实渲染并补齐一次联动刷新。"""
        if not bool(getattr(self, "_zoom_freeze_active", False)):
            return

        # 先将累计的缩放一次性应用到 view（overlay 仍可见，避免“瞬间回到旧倍率”的闪烁）。
        pending = float(getattr(self, "_zoom_freeze_pending_factor", 1.0) or 1.0)
        pivot = getattr(self, "_zoom_freeze_last_pivot", None)
        if pivot is None:
            vp = self.view.viewport()
            pivot = QtCore.QPointF(float(vp.width()) * 0.5, float(vp.height()) * 0.5)
        if abs(float(pending) - 1.0) > 1e-6:
            self._apply_zoom_factor_at_pivot(float(pending), pivot)
        self._zoom_freeze_pending_factor = 1.0
        self._zoom_freeze_last_pivot = None

        overlay = getattr(self, "_zoom_freeze_overlay", None)
        end = getattr(overlay, "end_freeze", None) if overlay is not None else None
        if callable(end):
            end()

        self._zoom_freeze_active = False

        if self._saved_update_mode_zoom is not None:
            self.view.setViewportUpdateMode(self._saved_update_mode_zoom)
            self._saved_update_mode_zoom = None

        # 缩放完成：在首帧绘制前先同步 scale_hint，避免 LOD/命中测试口径滞后一帧。
        scene = self.view.scene()
        if scene is not None:
            current_scale = float(self.view.transform().m11())
            set_hint = getattr(scene, "set_view_scale_hint", None)
            if callable(set_hint):
                set_hint(current_scale)
            else:
                setattr(scene, "view_scale_hint", current_scale)

        # 恢复后补齐一次背景/叠层联动
        self.invalidate_background()
        self.view.viewport().update()
        if self.view.mini_map:
            self.view.mini_map.update_viewport_rect()
        if self.view.overlay_manager:
            self.view.overlay_manager.request_position_update()
        self._sync_ydebug_tooltip_position()

    def _apply_zoom_factor_at_pivot(self, factor: float, pivot: QtCore.QPointF) -> None:
        """在指定 viewport 坐标 pivot 处应用缩放（保持 pivot 下的场景点不漂移）。"""
        if factor <= 0.0:
            return
        if abs(float(factor) - 1.0) < 1e-9:
            return
        pivot_pt = QtCore.QPoint(int(pivot.x()), int(pivot.y()))
        old_anchor = self.view.transformationAnchor()
        old_resize_anchor = self.view.resizeAnchor()
        # 手动锚点缩放：避免 AnchorUnderMouse 在“滚轮停止后”因鼠标位置变化导致最终结果跳一下
        self.view.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
        self.view.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
        old_scene_pos = self.view.mapToScene(pivot_pt)
        self.view.scale(float(factor), float(factor))
        new_scene_pos = self.view.mapToScene(pivot_pt)
        delta = new_scene_pos - old_scene_pos
        self.view.translate(float(delta.x()), float(delta.y()))
        self.view.setTransformationAnchor(old_anchor)
        self.view.setResizeAnchor(old_resize_anchor)
    
    def begin_pan_frame_settings(self) -> None:
        """在开始画布拖拽时，暂时调整渲染提示以降低重绘成本。"""
        # 若缩放静态快照仍在生效，先结束并恢复，避免保存/恢复 update mode 时拿到错误值。
        if bool(getattr(self, "_zoom_freeze_active", False)):
            self._end_zoom_freeze()
        # 进入拖拽平移：取消滚轮缩放交互态，避免 debounce timer 在拖拽中触发额外背景失效。
        self._cancel_wheel_zoom_interaction()
        # 保存当前设置
        self._saved_cache_mode = self.view.cacheMode()
        self._saved_update_mode = self.view.viewportUpdateMode()
        self._saved_render_hints_pan = self.view.renderHints()
        self._saved_interactive_pan = self.view.isInteractive()

        # 极致：拖拽平移期间冻结为静态快照（可选）
        from engine.configs.settings import settings as _settings

        self._pan_freeze_active = False
        if bool(getattr(_settings, "GRAPH_PAN_FREEZE_VIEWPORT_ENABLED", False)):
            overlay = getattr(self, "_pan_freeze_overlay", None)
            if overlay is None:
                from app.ui.graph.graph_view.overlays.pan_freeze_overlay import PanFreezeOverlay

                overlay = PanFreezeOverlay(self.view)
                self._pan_freeze_overlay = overlay
            monitor = None
            if bool(getattr(self.view, "_perf_panel_enabled", False)):
                monitor = getattr(self.view, "_perf_monitor", None)
            t0 = time.perf_counter() if monitor is not None else 0.0
            begin = getattr(overlay, "begin_freeze", None)
            if callable(begin):
                begin()
                self._pan_freeze_active = True
                # 确保覆盖层位于 viewport 之上（否则看起来“没有静态”）。
                if hasattr(overlay, "raise_"):
                    overlay.raise_()
                # 禁用视图更新：拖拽过程中不重绘场景（覆盖层负责显示）
                self.view.setViewportUpdateMode(QtWidgets.QGraphicsView.ViewportUpdateMode.NoViewportUpdate)
                # 置顶：保持右上角控件/小地图在覆盖层之上
                try_raise = getattr(self.view, "mini_map", None)
                if try_raise is not None and hasattr(try_raise, "raise_"):
                    try_raise.raise_()
                from app.ui.graph.graph_view.top_right.controls_manager import TopRightControlsManager

                TopRightControlsManager.raise_all(self.view)
                perf_overlay = getattr(self.view, "_perf_overlay", None)
                if perf_overlay is not None and hasattr(perf_overlay, "raise_") and perf_overlay.isVisible():
                    perf_overlay.raise_()
                search_overlay = getattr(self.view, "search_overlay", None)
                if search_overlay is not None and hasattr(search_overlay, "raise_") and search_overlay.isVisible():
                    search_overlay.raise_()
                if monitor is not None:
                    monitor.record_ms(
                        "controller.pan_freeze.capture",
                        (time.perf_counter() - float(t0)) * 1000.0,
                    )

        # 关键：平移时禁止场景项交互。
        #
        # 说明：GraphView 的右键/中键/空格手抓平移，会通过“伪造左键”来复用 Qt 内建的
        # ScrollHandDrag 行为；若鼠标按在节点/连线等图形项上，伪造左键 press 可能会被图形项
        # 优先吃掉，导致 ScrollHandDrag 未进入拖拽状态，从而出现“按在节点/线上就拖不动”。
        #
        # 在平移期间关闭 interactive，可确保事件不派发给图形项，画布平移在任意位置都能启动。
        self.view.setInteractive(False)

        # 同步场景的“平移状态”：用于临时隐藏端口/⚙/+ 与跳过 YDebug 叠层绘制。
        scene = self.view.scene()
        set_panning = getattr(scene, "set_view_panning", None) if scene is not None else None
        if callable(set_panning):
            set_panning(True)

        # 关键：平移期间禁用背景缓存。
        #
        # 在部分 Windows 环境下，`CacheBackground` 配合 `ScrollHandDrag` 的滚动像素优化会让网格出现
        # “分块错位/陈旧像素”观感（类似老系统拖拽窗口时的背景撕裂）。
        #
        # 这里仅在拖拽期间关闭缓存：
        # - 视觉上网格始终由 SceneOverlayMixin.drawBackground 按当前视口实时绘制，避免错位；
        # - 性能上仍保留 MinimalViewportUpdate（默认），避免将平移退化为全量重绘。
        self.view.setCacheMode(QtWidgets.QGraphicsView.CacheModeFlag.CacheNone)

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
        if self._saved_interactive_pan is not None:
            self.view.setInteractive(self._saved_interactive_pan)
            self._saved_interactive_pan = None
        # 恢复拖拽前的渲染提示配置
        if self._saved_render_hints_pan is not None:
            self.view.setRenderHints(self._saved_render_hints_pan)
            self._saved_render_hints_pan = None

        # 先恢复场景的“平移状态”，让端口/叠层立即回到正常显示（避免松手后短暂空白）。
        scene = self.view.scene()
        set_panning = getattr(scene, "set_view_panning", None) if scene is not None else None
        if callable(set_panning):
            set_panning(False)

        # 结束静态快照：恢复真实渲染（update mode 已在上方恢复）
        if bool(getattr(self, "_pan_freeze_active", False)):
            overlay = getattr(self, "_pan_freeze_overlay", None)
            end = getattr(overlay, "end_freeze", None) if overlay is not None else None
            if callable(end):
                end()
            self._pan_freeze_active = False
        # 清理一次缓存内容并请求重绘背景
        self.invalidate_background()
        self._run_pan_followups_immediately()
    
    def begin_interaction_frame_settings(self) -> None:
        """在左键交互（节点拖拽/框选/连线预览）期间，临时调整缓存/更新模式以避免残影与卡顿。

        说明：
        - 常规编辑场景：使用 `FullViewportUpdate` 可最大程度规避残影（代价是大图下更耗性能）。
        - 超大图/快速预览（fast_preview_mode）：避免强制全视口重绘，保持 `MinimalViewportUpdate`
          以显著降低拖拽/框选期间的卡顿。
        """
        if self._interaction_elevated:
            return
        self._saved_cache_mode_interaction = self.view.cacheMode()
        self._saved_update_mode_interaction = self.view.viewportUpdateMode()
        self.view.setCacheMode(QtWidgets.QGraphicsView.CacheModeFlag.CacheNone)

        scene = self.view.scene()
        is_fast_preview_mode = bool(getattr(scene, "fast_preview_mode", False)) if scene is not None else False
        update_mode = (
            QtWidgets.QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate
            if is_fast_preview_mode
            else QtWidgets.QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )
        self.view.setViewportUpdateMode(update_mode)
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
            from app.ui.graph.graph_view.assembly.view_assembly import ViewAssembly
            ViewAssembly.update_mini_map_position(self.view)
            self.view.mini_map.raise_()
            self.view.mini_map.update_viewport_rect()
        if self.view.overlay_manager:
            self.view.overlay_manager.request_position_update()
        self._sync_ydebug_tooltip_position()
        self._last_pan_followup_ts = 0.0

