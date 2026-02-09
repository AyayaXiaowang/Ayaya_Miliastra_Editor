from __future__ import annotations

import time

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation import fonts as ui_fonts
from app.ui.graph.graph_palette import GraphPalette
from app.ui.graph.items.port_type_popup_item import PortTypePopupItem
from engine.type_registry import TYPE_FLOW
from engine.configs.settings import settings as _settings_ui


class PortSettingsButton(QtWidgets.QGraphicsItem):
    """端口“设置/查看类型”按钮（画布内小齿轮）。

    设计目标：
    - 轻量：使用 QGraphicsItem 自绘，避免 QGraphicsProxyWidget 带来的性能与焦点复杂度。
    - 无副作用：点击仅弹出信息对话框，不修改模型。
    - 交互明确：hover 高亮 + toolTip。
    """

    DEFAULT_SIZE_PX = 14

    def __init__(
        self,
        node_item,
        port_name: str,
        *,
        is_input: bool,
        is_flow: bool,
        size_px: int | None = None,
    ) -> None:
        # QGraphicsItem 在 __init__ 过程中可能调用 boundingRect，因此按 super() 之前初始化尺寸相关字段
        self.button_size = int(size_px or self.DEFAULT_SIZE_PX)
        self.is_hovered = False

        super().__init__(parent=node_item)

        self.node_item = node_item
        self.port_name = str(port_name)
        self.is_input = bool(is_input)
        self.is_flow = bool(is_flow)

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.LeftButton)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        side = "输入" if self.is_input else "输出"
        self.setToolTip(f"查看端口类型：{side} · {self.port_name}")
        # 端口(20)与“+”(25)之上，避免被标签/连线遮挡
        self.setZValue(26)

    def boundingRect(self) -> QtCore.QRectF:
        half = self.button_size / 2
        return QtCore.QRectF(-half, -half, self.button_size, self.button_size)

    def shape(self) -> QtGui.QPainterPath:  # type: ignore[override]
        """命中测试形状。

        LOD：当缩放低于阈值时返回空 shape，避免“按钮不可见但仍可被点击”。
        """
        scene_ref_for_perf = self.scene()
        monitor = getattr(scene_ref_for_perf, "_perf_monitor", None) if scene_ref_for_perf is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.shape.port_settings.calls", 1)

        if bool(getattr(_settings_ui, "GRAPH_LOD_ENABLED", True)):
            scene_ref = self.scene()
            scale_hint = float(getattr(scene_ref, "view_scale_hint", 1.0) or 1.0) if scene_ref is not None else 1.0
            details_min_scale = float(getattr(_settings_ui, "GRAPH_LOD_NODE_DETAILS_MIN_SCALE", 0.55))
            if scale_hint < details_min_scale:
                if monitor is not None and callable(accum):
                    accum("items.shape.port_settings.lod_skip", int(time.perf_counter_ns() - int(t_total0)))
                return QtGui.QPainterPath()
        path = QtGui.QPainterPath()
        path.addRoundedRect(self.boundingRect(), 3.0, 3.0)
        if monitor is not None and callable(accum):
            accum("items.shape.port_settings.total", int(time.perf_counter_ns() - int(t_total0)))
        return path

    def paint(self, painter: QtGui.QPainter | None, option, widget=None) -> None:
        if painter is None:
            return
        scene_ref_for_perf = self.scene()
        monitor = getattr(scene_ref_for_perf, "_perf_monitor", None) if scene_ref_for_perf is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        track = getattr(monitor, "track_slowest", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.paint.port_settings.calls", 1)

        # LOD：低倍率缩放时隐藏端口“⚙”按钮（节点仅保留标题栏与标题文本）
        if bool(getattr(_settings_ui, "GRAPH_LOD_ENABLED", True)):
            t0 = time.perf_counter_ns() if monitor is not None else 0
            scale_hint = float(painter.worldTransform().m11())
            details_min_scale = float(getattr(_settings_ui, "GRAPH_LOD_NODE_DETAILS_MIN_SCALE", 0.55))
            if scale_hint < details_min_scale:
                if monitor is not None and callable(accum):
                    accum("items.paint.port_settings.lod_gate", int(time.perf_counter_ns() - int(t0)))
                    dt_total_ns = int(time.perf_counter_ns() - int(t_total0))
                    accum("items.paint.port_settings.total", dt_total_ns)
                return
            if monitor is not None and callable(accum):
                accum("items.paint.port_settings.lod_gate", int(time.perf_counter_ns() - int(t0)))
        rect = self.boundingRect()

        if self.is_hovered:
            bg = QtGui.QColor(GraphPalette.BTN_PRIMARY_HOVER)
            border = QtGui.QColor(GraphPalette.BTN_PRIMARY)
            icon_color = QtGui.QColor(GraphPalette.TEXT_BRIGHT)
        else:
            bg = QtGui.QColor(GraphPalette.INPUT_BG)
            bg.setAlpha(220)
            border = QtGui.QColor(GraphPalette.BORDER_SUBTLE)
            icon_color = QtGui.QColor(GraphPalette.TEXT_SECONDARY)

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtGui.QPen(border, 1))
        painter.setBrush(QtGui.QBrush(bg))
        painter.drawRoundedRect(rect, 3, 3)

        painter.setPen(icon_color)
        painter.setFont(ui_fonts.emoji_font(9))
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, "⚙")
        if monitor is not None and callable(accum):
            dt_total_ns = int(time.perf_counter_ns() - int(t_total0))
            accum("items.paint.port_settings.total", dt_total_ns)
            if callable(track):
                node_obj = getattr(getattr(self, "node_item", None), "node", None)
                node_id = str(getattr(node_obj, "id", "") or "")
                track(f"gear:{node_id}.{self.port_name}", dt_total_ns)

    def hoverEnterEvent(self, event) -> None:
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent | None) -> None:
        if event is None:
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._toggle_port_type_popup()
            event.accept()
            return
        super().mousePressEvent(event)

    def _toggle_port_type_popup(self) -> None:
        """在画布内显示/隐藏端口类型气泡（同一时间只保留一个）。"""
        scene = self.scene()
        if not isinstance(scene, QtWidgets.QGraphicsScene):
            return

        from PyQt6 import sip
        from typing import Any, cast

        scene_any = cast(Any, scene)
        existing = getattr(scene_any, "_port_type_popup_item", None)
        token = f"{getattr(self.node_item.node, 'id', '')}:{self.port_name}:{'in' if self.is_input else 'out'}"

        if existing is not None:
            existing_token = getattr(existing, "_popup_token", None)
            if not sip.isdeleted(existing):
                scene.removeItem(existing)
            scene_any._port_type_popup_item = None
            # 同一端口再次点击：视为关闭
            if existing_token == token:
                return

        resolved_type = self._resolve_effective_port_type(scene)
        side = "输入" if self.is_input else "输出"
        lines = [f"{side}：{self.port_name}", f"类型：{resolved_type}"]
        popup = PortTypePopupItem(lines)
        popup._popup_token = token  # type: ignore[attr-defined]
        scene.addItem(popup)
        scene_any._port_type_popup_item = popup

        anchor = self.mapToScene(QtCore.QPointF(0.0, 0.0))
        rect = popup.boundingRect()
        margin = 8.0
        if self.is_input:
            x = float(anchor.x()) + float(self.button_size) / 2 + margin
        else:
            x = float(anchor.x()) - float(self.button_size) / 2 - margin - float(rect.width())
        y = float(anchor.y()) - float(rect.height()) / 2
        popup.setPos(float(x), float(y))

    def _resolve_effective_port_type(self, scene: QtWidgets.QGraphicsScene) -> str:
        """解析端口“当前图真实生效”的类型（优先覆盖表，其次推断，再回退到声明）。"""
        if self.is_flow:
            return TYPE_FLOW
        from app.ui.graph.items.port_type_resolver import resolve_effective_port_type_for_scene

        node_model = getattr(self.node_item, "node", None)
        if node_model is None:
            return "泛型"

        return resolve_effective_port_type_for_scene(
            scene,
            node_model,
            self.port_name,
            is_input=self.is_input,
            is_flow=self.is_flow,
        )


__all__ = ["PortSettingsButton"]


