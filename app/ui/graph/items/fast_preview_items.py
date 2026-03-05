from __future__ import annotations

import time

from dataclasses import dataclass

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation import fonts as ui_fonts
from app.ui.graph.graph_palette import GraphPalette
from app.ui.graph.items.node_item import NodeGraphicsItem
from engine.configs.settings import settings
from engine.graph.models.graph_model import NodeModel


@dataclass(frozen=True, slots=True)
class PreviewEdgeEndpoint:
    """轻量连线端点（用于快速预览）。

    说明：
    - 该对象仅提供 EdgeGraphicsItem/SceneModelOpsMixin 常用字段子集：node_item/name/is_flow/scenePos。
    - 不参与端口类型与连线规则，仅用于绘制与命中。
    """

    node_item: NodeGraphicsItem
    name: str
    is_flow: bool = False

    def scenePos(self) -> QtCore.QPointF:  # noqa: N802 - 对齐 Qt 命名习惯
        rect = self.node_item.sceneBoundingRect()
        return rect.center()


class FastPreviewNodeGraphicsItem(NodeGraphicsItem):
    """轻量节点图形项：只画“节点框 + 标题”，用于大图预览加速。

    设计目标：
    - 不创建端口与行内常量编辑控件（QGraphicsProxyWidget），避免 1000+ 节点时 UI 卡顿；
    - 仍保持 NodeGraphicsItem 类型，以复用既有“点击/双击/高亮/定位”路径；
    - 允许场景在可交互会话中拖拽节点（若上层允许），并由 SceneInteractionMixin 刷新预览连线。
    """

    _MIN_WIDTH: float = 180.0
    _MAX_WIDTH: float = 360.0
    _HEIGHT: float = 54.0

    def __init__(self, node: NodeModel):
        super().__init__(node)
        # 预览项优先使用缓存（降低大图缩放/平移时的重绘成本）
        self.setCacheMode(QtWidgets.QGraphicsItem.CacheMode.DeviceCoordinateCache)
        # 节点级“展开详情”：仅在快速预览模式下使用，展开后会临时创建端口与常量控件（只读展示）。
        self._preview_detail_expanded: bool = False
        self._preview_toggle_rect: QtCore.QRectF = QtCore.QRectF()

    def _layout_ports(self) -> None:  # type: ignore[override]
        """快速预览端口布局：

        - 默认（收起）：不创建端口与行内控件，只设置矩形大小；
        - 展开：复用 NodeGraphicsItem 的完整布局，但对“快速预览连线”做兼容处理。
        """
        if self._preview_detail_expanded:
            # 展开详情时不使用预览缓存（节点内容变化更频繁，且缓存会放大内存占用）。
            self.setCacheMode(QtWidgets.QGraphicsItem.CacheMode.NoCache)
            super()._layout_ports()
            self._lock_down_interaction_for_preview_detail()
            return

        # 收起：清理旧的端口/控件（若之前处于展开状态），然后只保留标题框。
        self.prepareGeometryChange()
        if hasattr(self, "_reset_ports_and_controls"):
            self._reset_ports_and_controls()
        if getattr(self, "_add_port_button", None) is not None:
            button_item = self._add_port_button
            button_scene = button_item.scene() if button_item is not None else None
            if button_scene is not None:
                button_scene.removeItem(button_item)
            self._add_port_button = None

        self.setCacheMode(QtWidgets.QGraphicsItem.CacheMode.DeviceCoordinateCache)
        title_text = str(getattr(self.node, "title", "") or "")
        font_metrics = QtGui.QFontMetrics(ui_fonts.ui_font(10, bold=True))
        desired_width = float(font_metrics.horizontalAdvance(title_text) + 44)
        width = min(self._MAX_WIDTH, max(self._MIN_WIDTH, desired_width))
        self._rect = QtCore.QRectF(0, 0, width, float(self._HEIGHT))
        self.update()

    def paint(self, painter: QtGui.QPainter | None, option, widget=None) -> None:  # type: ignore[override]
        if painter is None:
            return

        scene_ref = self.scene()
        monitor = getattr(scene_ref, "_perf_monitor", None) if scene_ref is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        track = getattr(monitor, "track_slowest", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.paint.fast_node.calls", 1)

        # 展开态：交给完整 NodeGraphicsItem 绘制，再叠加“收起”按钮
        if self._preview_detail_expanded:
            if monitor is not None and callable(accum):
                t0 = time.perf_counter_ns()
                super().paint(painter, option, widget)
                accum("items.paint.fast_node.expanded_super", int(time.perf_counter_ns() - int(t0)))
                t0 = time.perf_counter_ns()
                self._paint_preview_detail_toggle(painter, expanded=True)
                accum("items.paint.fast_node.toggle", int(time.perf_counter_ns() - int(t0)))
                dt_ns = int(time.perf_counter_ns() - int(t_total0))
                accum("items.paint.fast_node.total", dt_ns)
                if callable(track):
                    track(f"fast_node:{getattr(self.node, 'id', '')}", dt_ns)
            else:
                super().paint(painter, option, widget)
                self._paint_preview_detail_toggle(painter, expanded=True)
            return

        rect = self.boundingRect()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)

        # 搜索命中描边：仅对未选中节点绘制
        if hasattr(self, "_paint_search_highlight_outline"):
            self._paint_search_highlight_outline(painter, rect, corner_radius=8.0)

        bg_color = QtGui.QColor(GraphPalette.NODE_CONTENT_BG)
        bg_color.setAlpha(int(255 * float(getattr(settings, "GRAPH_NODE_CONTENT_ALPHA", 0.7))))
        border_color = (
            QtGui.QColor(GraphPalette.EDGE_DATA_SELECTED)
            if self.isSelected()
            else QtGui.QColor(GraphPalette.NODE_CONTENT_BORDER)
        )

        painter.setBrush(bg_color)
        painter.setPen(QtGui.QPen(border_color, 1 if not self.isSelected() else 2))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)

        painter.setFont(ui_fonts.ui_font(10, bold=True))
        painter.setPen(QtGui.QColor(GraphPalette.TEXT_LABEL))
        title_text = str(getattr(self.node, "title", "") or "")
        painter.drawText(
            rect.adjusted(12, 0, -12, 0),
            QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
            title_text,
        )

        # 入口必须“可发现”：在快速预览节点上始终绘制展开按钮（仅一个小矩形+符号，成本可控）。
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            self._paint_preview_detail_toggle(painter, expanded=False)
            accum("items.paint.fast_node.toggle", int(time.perf_counter_ns() - int(t0)))
            dt_ns = int(time.perf_counter_ns() - int(t_total0))
            accum("items.paint.fast_node.total", dt_ns)
            if callable(track):
                track(f"fast_node:{getattr(self.node, 'id', '')}", dt_ns)
        else:
            self._paint_preview_detail_toggle(painter, expanded=False)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event is None:
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            toggle_rect = self._preview_toggle_rect
            if toggle_rect is not None and toggle_rect.contains(event.pos()):
                scene_ref = self.scene()
                toggle_fn = getattr(scene_ref, "toggle_fast_preview_node_detail", None)
                if callable(toggle_fn):
                    toggle_fn(str(getattr(self.node, "id", "") or ""))
                else:
                    self.set_preview_detail_expanded(not self._preview_detail_expanded)
                event.accept()
                return
        super().mousePressEvent(event)

    # --- 节点级展开/收起（供 GraphScene 调用） ---

    @property
    def is_preview_detail_expanded(self) -> bool:
        return bool(self._preview_detail_expanded)

    def set_preview_detail_expanded(self, expanded: bool) -> None:
        new_state = bool(expanded)
        if self._preview_detail_expanded == new_state:
            return
        self._preview_detail_expanded = new_state
        self._layout_ports()
        self.update()

    def _update_edges_after_layout(self, edges_to_update: list[tuple]) -> None:  # type: ignore[override]
        """兼容快速预览连线：

        - 对 `FastPreviewEdgeGraphicsItem`：不能把 src/dst 改成端口图元（会破坏预览边），只需刷新路径；
        - 对普通 `EdgeGraphicsItem`：沿用父类逻辑（更新端口端点并重算路径）。
        """
        non_preview_edges: list[tuple] = []
        for edge_entry in edges_to_update:
            edge_item = edge_entry[0]
            if isinstance(edge_item, FastPreviewEdgeGraphicsItem):
                edge_item.update_path()
            else:
                non_preview_edges.append(edge_entry)
        if non_preview_edges:
            super()._update_edges_after_layout(non_preview_edges)

    def _lock_down_interaction_for_preview_detail(self) -> None:
        """展开态只读展示：避免在快速预览模式下出现“看起来能编辑/连线但不会落盘”的混乱体验。"""
        scene_ref = self.scene()
        if scene_ref is None or not bool(getattr(scene_ref, "fast_preview_mode", False)):
            return

        # 端口：禁用鼠标交互（阻止拖拽连线）
        for port_item in self.iter_all_ports():
            if hasattr(port_item, "setAcceptedMouseButtons"):
                port_item.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
            port_item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            port_item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

        # 常量控件：只读展示（允许选中复制，但禁止编辑/误改）
        constant_edits = getattr(self, "_constant_edits", None)
        if not isinstance(constant_edits, dict):
            return

        def _sync_embedded_constant_widget(widget: QtWidgets.QWidget | None) -> None:
            if widget is None:
                return
            if isinstance(widget, QtWidgets.QLineEdit):
                widget.setEnabled(True)
                widget.setReadOnly(True)
                return
            if isinstance(widget, QtWidgets.QTextEdit):
                widget.setEnabled(True)
                widget.setReadOnly(True)
                return
            if isinstance(widget, QtWidgets.QPlainTextEdit):
                widget.setEnabled(True)
                widget.setReadOnly(True)
                return
            if isinstance(widget, QtWidgets.QComboBox):
                widget.setEnabled(False)
                return

            widget.setEnabled(True)
            for line_edit in widget.findChildren(QtWidgets.QLineEdit):
                line_edit.setEnabled(True)
                line_edit.setReadOnly(True)
            for text_edit in widget.findChildren(QtWidgets.QTextEdit):
                text_edit.setEnabled(True)
                text_edit.setReadOnly(True)
            for plain_text_edit in widget.findChildren(QtWidgets.QPlainTextEdit):
                plain_text_edit.setEnabled(True)
                plain_text_edit.setReadOnly(True)
            for combo in widget.findChildren(QtWidgets.QComboBox):
                combo.setEnabled(False)

        for edit_item in constant_edits.values():
            if hasattr(edit_item, "setTextInteractionFlags"):
                edit_item.setTextInteractionFlags(
                    QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
                    | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
                )
            if hasattr(edit_item, "setFlag"):
                edit_item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
            if hasattr(edit_item, "widget") and callable(getattr(edit_item, "widget")):
                embedded_widget = edit_item.widget()
                if isinstance(embedded_widget, QtWidgets.QWidget):
                    _sync_embedded_constant_widget(embedded_widget)
            if hasattr(edit_item, "setAcceptedMouseButtons"):
                # 仅允许左键选中（复制），屏蔽右键菜单等“看起来能改”的交互。
                edit_item.setAcceptedMouseButtons(QtCore.Qt.MouseButton.LeftButton)

    def _paint_preview_detail_toggle(self, painter: QtGui.QPainter, *, expanded: bool) -> None:
        """绘制右上角的“展开/收起”小按钮。"""
        rect = self.boundingRect()
        button_width = 22.0
        button_height = 22.0
        margin = 6.0
        x = rect.right() - margin - button_width
        y = rect.top() + margin

        # 避让：布局Y调试感叹号（SceneOverlayMixin 在节点右上角绘制 "!" 圆徽标）
        # 该徽标绘制在前景层，会遮挡节点自身绘制的按钮；因此按钮需排在其左侧。
        if bool(getattr(settings, "SHOW_LAYOUT_Y_DEBUG", False)):
            ydebug_icon_size = 28.0
            ydebug_spacing = 4.0
            x = x - ydebug_icon_size - ydebug_spacing
            # 纵向居中对齐到 28px 的徽标
            y = y + (ydebug_icon_size - button_height) * 0.5

        self._preview_toggle_rect = QtCore.QRectF(float(x), float(y), button_width, button_height)

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QtGui.QPen(QtGui.QColor(GraphPalette.NODE_CONTENT_BORDER), 1))
        painter.setBrush(
            QtGui.QColor(GraphPalette.EDGE_DATA_SELECTED)
            if expanded
            else QtGui.QColor(GraphPalette.INPUT_BG)
        )
        painter.drawRoundedRect(self._preview_toggle_rect, 3, 3)

        painter.setPen(QtGui.QColor(GraphPalette.TEXT_LABEL))
        painter.setFont(ui_fonts.ui_font(10, bold=True))
        # 字符尽量用 ASCII，避免字体回退导致不可见
        icon_text = "-" if expanded else "+"
        painter.drawText(
            self._preview_toggle_rect,
            QtCore.Qt.AlignmentFlag.AlignCenter,
            icon_text,
        )
        painter.restore()


class FastPreviewEdgeGraphicsItem(QtWidgets.QGraphicsPathItem):
    """轻量连线图形项：按节点中心/边界绘制，不依赖端口图元。"""

    # 命中区域宽度（单位：场景坐标）。该宽度只影响选择/点击命中，不影响绘制线宽。
    _HIT_TEST_STROKE_WIDTH_MIN: float = 1.5

    def __init__(self, src: PreviewEdgeEndpoint, dst: PreviewEdgeEndpoint, edge_id: str):
        super().__init__()
        self.src = src
        self.dst = dst
        self.edge_id = str(edge_id)
        self.setZValue(4)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self._update_pen()
        self.update_path()

        # 命中形状缓存：shape() 在鼠标命中与框选中可能被频繁调用。
        # 预览边数量往往更大，缓存能显著降低反复 stroker 的成本。
        self._cached_hit_shape: QtGui.QPainterPath | None = None
        self._cached_hit_shape_source_path: QtGui.QPainterPath | None = None
        self._cached_hit_shape_width: float | None = None

    def _update_pen(self) -> None:
        if self.isSelected():
            color = QtGui.QColor(GraphPalette.EDGE_DATA_SELECTED)
            width = 3
        else:
            color = QtGui.QColor(GraphPalette.EDGE_DATA)
            width = 1
        self.setPen(QtGui.QPen(color, width))
        self._invalidate_hit_shape_cache()

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            QtCore.QTimer.singleShot(0, self._update_pen)
        return super().itemChange(change, value)

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:  # type: ignore[override]
        """重写 paint，移除 Qt 默认的选中虚线框。

        说明：快速预览边仍通过笔刷颜色/线宽表达选中态；不使用 QGraphicsPathItem 默认的选中绘制，
        避免在长连线/大图下出现“巨大选中框”影响观感。
        """
        scene_ref = self.scene()
        monitor = getattr(scene_ref, "_perf_monitor", None) if scene_ref is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        track = getattr(monitor, "track_slowest", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.paint.fast_edge.calls", 1)

        # LOD：低倍率缩放时隐藏非选中的连线，显著降低超大图的绘制成本
        if bool(getattr(settings, "GRAPH_LOD_ENABLED", True)):
            t0 = time.perf_counter_ns() if monitor is not None else 0
            scale_hint = float(painter.worldTransform().m11())
            edge_min_scale = float(getattr(settings, "GRAPH_LOD_EDGE_MIN_SCALE", 0.22))
            if scale_hint < edge_min_scale and (not self.isSelected()):
                if monitor is not None and callable(accum):
                    accum("items.paint.fast_edge.lod_gate", int(time.perf_counter_ns() - int(t0)))
                    dt_ns = int(time.perf_counter_ns() - int(t_total0))
                    accum("items.paint.fast_edge.total", dt_ns)
                    if callable(track):
                        track(f"fast_edge:{self.edge_id}", dt_ns)
                return
            if monitor is not None and callable(accum):
                accum("items.paint.fast_edge.lod_gate", int(time.perf_counter_ns() - int(t0)))

        option.state &= ~QtWidgets.QStyle.StateFlag.State_Selected
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            super().paint(painter, option, widget)
            accum("items.paint.fast_edge.super", int(time.perf_counter_ns() - int(t0)))
            dt_ns = int(time.perf_counter_ns() - int(t_total0))
            accum("items.paint.fast_edge.total", dt_ns)
            if callable(track):
                track(f"fast_edge:{self.edge_id}", dt_ns)
        else:
            super().paint(painter, option, widget)

    def _invalidate_hit_shape_cache(self) -> None:
        self._cached_hit_shape = None
        self._cached_hit_shape_source_path = None
        self._cached_hit_shape_width = None

    def _get_hit_test_stroke_width(self) -> float:
        """获取用于命中测试的描边宽度（与绘制 pen 宽度解耦）。"""
        pen_width = float(self.pen().widthF()) if self.pen() is not None else 0.0
        # 命中宽度不应小于视觉线宽的 75%，否则会出现“线看得见但点不到”的体验问题。
        width_by_pen = pen_width * 0.75 if pen_width > 0.0 else 0.0
        return max(self._HIT_TEST_STROKE_WIDTH_MIN, width_by_pen)

    def shape(self) -> QtGui.QPainterPath:  # type: ignore[override]
        """返回用于命中测试的形状路径（用于点击/框选）。

        在超大图与低倍率缩放下，命中测试往往是交互卡顿的重要来源。
        因此这里与 EdgeGraphicsItem 保持一致：低倍率时对非选中边返回空 shape，
        以降低 QGraphicsScene 的 hit-test 成本。
        """
        scene_ref_for_perf = self.scene()
        monitor = getattr(scene_ref_for_perf, "_perf_monitor", None) if scene_ref_for_perf is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        track = getattr(monitor, "track_slowest", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.shape.fast_edge.calls", 1)

        # LOD：低倍率缩放时降低命中测试成本（非选中连线直接返回空 shape）
        if bool(getattr(settings, "GRAPH_LOD_ENABLED", True)):
            scene_ref = self.scene()
            scale_hint = (
                float(getattr(scene_ref, "view_scale_hint", 1.0) or 1.0)
                if scene_ref is not None
                else 1.0
            )
            hit_min_scale = float(getattr(settings, "GRAPH_LOD_EDGE_HITTEST_MIN_SCALE", 0.28))
            if scale_hint < hit_min_scale and (not self.isSelected()):
                if monitor is not None and callable(accum):
                    accum("items.shape.fast_edge.lod_skip", int(time.perf_counter_ns() - int(t_total0)))
                return QtGui.QPainterPath()

        current_path = self.path()
        if current_path.isEmpty():
            return QtGui.QPainterPath()

        hit_width = float(self._get_hit_test_stroke_width())
        if (
            self._cached_hit_shape is not None
            and self._cached_hit_shape_source_path == current_path
            and self._cached_hit_shape_width == hit_width
        ):
            if callable(inc):
                inc("items.shape.fast_edge.cache_hit", 1)
            if monitor is not None and callable(accum):
                dt_ns = int(time.perf_counter_ns() - int(t_total0))
                accum("items.shape.fast_edge.total", dt_ns)
                if callable(track):
                    track(f"fast_edge.shape:{self.edge_id}", dt_ns)
            return self._cached_hit_shape

        if callable(inc):
            inc("items.shape.fast_edge.cache_miss", 1)
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(hit_width)
        stroker.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            hit_shape = stroker.createStroke(current_path)
            accum("items.shape.fast_edge.stroker", int(time.perf_counter_ns() - int(t0)))
        else:
            hit_shape = stroker.createStroke(current_path)

        self._cached_hit_shape = hit_shape
        self._cached_hit_shape_source_path = QtGui.QPainterPath(current_path)
        self._cached_hit_shape_width = hit_width
        if monitor is not None and callable(accum):
            dt_ns = int(time.perf_counter_ns() - int(t_total0))
            accum("items.shape.fast_edge.total", dt_ns)
            if callable(track):
                track(f"fast_edge.shape:{self.edge_id}", dt_ns)
        return hit_shape

    def update_path(self) -> None:
        """根据两端节点矩形计算一条轻量曲线。"""
        scene_ref = self.scene()
        monitor = getattr(scene_ref, "_perf_monitor", None) if scene_ref is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        track = getattr(monitor, "track_slowest", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.update_path.fast_edge.calls", 1)

        src_rect = self.src.node_item.sceneBoundingRect()
        dst_rect = self.dst.node_item.sceneBoundingRect()

        start = QtCore.QPointF(float(src_rect.right()), float(src_rect.center().y()))
        end = QtCore.QPointF(float(dst_rect.left()), float(dst_rect.center().y()))

        path = QtGui.QPainterPath(start)
        dx = abs(float(end.x() - start.x())) * 0.5
        c1 = QtCore.QPointF(float(start.x() + dx), float(start.y()))
        c2 = QtCore.QPointF(float(end.x() - dx), float(end.y()))
        path.cubicTo(c1, c2, end)
        self.setPath(path)
        self._invalidate_hit_shape_cache()
        if monitor is not None and callable(accum):
            dt_ns = int(time.perf_counter_ns() - int(t_total0))
            accum("items.update_path.fast_edge.total", dt_ns)
            if callable(track):
                track(f"fast_edge.update_path:{self.edge_id}", dt_ns)


