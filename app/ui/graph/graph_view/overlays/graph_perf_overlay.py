from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Deque, Dict, Iterable, List, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager

if TYPE_CHECKING:
    from app.ui.graph.graph_view import GraphView


@dataclass(frozen=True)
class PerfSeriesStats:
    name: str
    avg_ms: float
    max_ms: float
    last_ms: float
    samples: int


@dataclass(frozen=True)
class PerfCountStats:
    name: str
    avg: float
    max: int
    last: int
    samples: int


class GraphPerfMonitor:
    """轻量性能采样器（用于 UI 交互卡顿定位）。

    设计目标：
    - 默认关闭；开启后允许在“每帧/每滚动回调”记录若干关键段耗时；
    - 只做滚动窗口聚合（均值/最大/最后一次），避免引入重度 profiler 的额外抖动；
    - 通过 `scope(name)` 以最小侵入方式插桩。
    """

    def __init__(self, *, window_size: int = 120):
        self._maxlen: int = int(window_size if window_size > 20 else 20)
        self._series_by_name: Dict[str, Deque[float]] = {}
        self._count_series_by_name: Dict[str, Deque[int]] = {}

        self._frame_intervals_s: Deque[float] = deque(maxlen=self._maxlen)
        self._last_frame_ts_s: float | None = None
        self._in_frame: bool = False
        # record_ms 在帧内的“本帧汇总”（用于快照/未归因开销，不改变 series 语义）
        self._frame_record_ms: Dict[str, float] = {}

        # per-frame accumulators（高频路径：只在帧末写入一次 series）
        self._frame_accum_ns: Dict[str, int] = {}
        self._frame_counts: Dict[str, int] = {}
        self._last_frame_counts: Dict[str, int] = {}
        self._last_frame_ms_by_name: Dict[str, float] = {}
        self._last_panning_frame_ms_by_name: Dict[str, float] = {}
        self._last_panning_frame_counts: Dict[str, int] = {}
        self._slowest_capacity: int = 8
        self._frame_slowest: List[Tuple[int, str]] = []  # (dt_ns, label)
        self._last_frame_slowest: List[Tuple[float, str]] = []  # (dt_ms, label)
        self._last_panning_frame_slowest: List[Tuple[float, str]] = []  # (dt_ms, label)

    def begin_frame(self) -> None:
        now = time.perf_counter()
        if self._last_frame_ts_s is not None:
            self._frame_intervals_s.append(float(now - self._last_frame_ts_s))
        self._last_frame_ts_s = now
        self._in_frame = True
        self._frame_record_ms.clear()
        self._frame_accum_ns.clear()
        self._frame_counts.clear()
        self._frame_slowest.clear()

    def record_ms(self, name: str, dt_ms: float) -> None:
        key = str(name or "").strip()
        if key == "":
            return
        if self._in_frame:
            self._frame_record_ms[key] = float(self._frame_record_ms.get(key, 0.0) or 0.0) + float(dt_ms)
        dq = self._series_by_name.get(key)
        if dq is None:
            dq = deque(maxlen=self._maxlen)
            self._series_by_name[key] = dq
        dq.append(float(dt_ms))

    def record_count(self, name: str, value: int) -> None:
        key = str(name or "").strip()
        if key == "":
            return
        dq = self._count_series_by_name.get(key)
        if dq is None:
            dq = deque(maxlen=self._maxlen)
            self._count_series_by_name[key] = dq
        dq.append(int(value))

    def scope(self, name: str) -> "_PerfScope":
        return _PerfScope(self, str(name))

    def accum_ns(self, name: str, dt_ns: int) -> None:
        key = str(name or "").strip()
        if key == "":
            return
        v = int(dt_ns)
        if v <= 0:
            return
        self._frame_accum_ns[key] = int(self._frame_accum_ns.get(key, 0) or 0) + v

    def inc(self, name: str, amount: int = 1) -> None:
        key = str(name or "").strip()
        if key == "":
            return
        inc = int(amount)
        if inc == 0:
            return
        self._frame_counts[key] = int(self._frame_counts.get(key, 0) or 0) + inc

    def track_slowest(self, label: str, dt_ns: int) -> None:
        lab = str(label or "").strip()
        if lab == "":
            return
        cap = int(self._slowest_capacity)
        if cap <= 0:
            return
        v = int(dt_ns)
        if v <= 0:
            return
        lst = self._frame_slowest
        if len(lst) < cap:
            lst.append((v, lab))
            i = len(lst) - 1
            while i > 0 and lst[i][0] > lst[i - 1][0]:
                lst[i], lst[i - 1] = lst[i - 1], lst[i]
                i -= 1
            return
        # list is kept sorted desc; last is the smallest
        if lst and v <= lst[-1][0]:
            return
        lst[-1] = (v, lab)
        i = len(lst) - 1
        while i > 0 and lst[i][0] > lst[i - 1][0]:
            lst[i], lst[i - 1] = lst[i - 1], lst[i]
            i -= 1

    def end_frame(self, *, is_panning: bool = False) -> None:
        frame_ms_by_name: Dict[str, float] = dict(self._frame_record_ms)
        # flush accumulators to time series（ms）
        for key, ns in list(self._frame_accum_ns.items()):
            ms = float(ns) / 1_000_000.0
            frame_ms_by_name[str(key)] = float(frame_ms_by_name.get(str(key), 0.0) or 0.0) + float(ms)
            self.record_ms(str(key), float(ms))
        for key, c in list(self._frame_counts.items()):
            self.record_count(str(key), int(c))
        self._last_frame_counts = dict(self._frame_counts)
        self._last_frame_ms_by_name = dict(frame_ms_by_name)
        if is_panning:
            self._last_panning_frame_ms_by_name = dict(frame_ms_by_name)
            self._last_panning_frame_counts = dict(self._frame_counts)
            self._last_panning_frame_slowest = [
                (float(ns) / 1_000_000.0, lab) for ns, lab in list(self._frame_slowest)
            ]
        self._last_frame_slowest = [(float(ns) / 1_000_000.0, lab) for ns, lab in list(self._frame_slowest)]
        self._frame_accum_ns.clear()
        self._frame_counts.clear()
        self._frame_slowest.clear()
        self._frame_record_ms.clear()
        self._in_frame = False

    def get_fps(self) -> float:
        if not self._frame_intervals_s:
            return 0.0
        avg_s = sum(self._frame_intervals_s) / float(len(self._frame_intervals_s))
        if avg_s <= 0.0:
            return 0.0
        return float(1.0 / avg_s)

    def get_series_stats(self, names: Iterable[str]) -> List[PerfSeriesStats]:
        out: List[PerfSeriesStats] = []
        for name in names:
            key = str(name or "").strip()
            if key == "":
                continue
            dq = self._series_by_name.get(key)
            if not dq:
                continue
            samples = int(len(dq))
            if samples <= 0:
                continue
            last_ms = float(dq[-1])
            avg_ms = float(sum(dq) / float(samples))
            max_ms = float(max(dq))
            out.append(
                PerfSeriesStats(
                    name=key,
                    avg_ms=avg_ms,
                    max_ms=max_ms,
                    last_ms=last_ms,
                    samples=samples,
                )
            )
        return out

    def get_all_series_stats(self) -> List[PerfSeriesStats]:
        return self.get_series_stats(self._series_by_name.keys())

    def get_count_series_stats(self, names: Iterable[str]) -> List[PerfCountStats]:
        out: List[PerfCountStats] = []
        for name in names:
            key = str(name or "").strip()
            if key == "":
                continue
            dq = self._count_series_by_name.get(key)
            if not dq:
                continue
            samples = int(len(dq))
            if samples <= 0:
                continue
            last_v = int(dq[-1])
            max_v = int(max(dq))
            avg_v = float(sum(dq) / float(samples))
            out.append(
                PerfCountStats(
                    name=key,
                    avg=avg_v,
                    max=max_v,
                    last=last_v,
                    samples=samples,
                )
            )
        return out

    def get_last_counts(self) -> Dict[str, int]:
        return dict(self._last_frame_counts)

    def get_last_slowest_items(self) -> List[Tuple[float, str]]:
        return list(self._last_frame_slowest)

    def get_last_frame_ms_by_name(self) -> Dict[str, float]:
        return dict(self._last_frame_ms_by_name)

    def get_last_panning_frame_ms_by_name(self) -> Dict[str, float]:
        return dict(self._last_panning_frame_ms_by_name)

    def get_last_panning_counts(self) -> Dict[str, int]:
        return dict(self._last_panning_frame_counts)

    def get_last_panning_slowest_items(self) -> List[Tuple[float, str]]:
        return list(self._last_panning_frame_slowest)


class _PerfScope:
    def __init__(self, monitor: GraphPerfMonitor, name: str):
        self._monitor = monitor
        self._name = name
        self._t0: float = 0.0

    def __enter__(self) -> "_PerfScope":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        dt_ms = (time.perf_counter() - float(self._t0)) * 1000.0
        self._monitor.record_ms(self._name, float(dt_ms))
        return False


class _PerfOverlayTextLabel(QtWidgets.QLabel):
    """性能面板文本：允许选择复制，同时尽量不阻塞画布交互。"""

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        # 右键/中键：优先让画布平移逻辑接管（ScrollHandDrag），避免面板“挡住拖拽”。
        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            event.ignore()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        buttons = event.buttons()
        if buttons & Qt.MouseButton.RightButton or buttons & Qt.MouseButton.MiddleButton:
            event.ignore()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            event.ignore()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[override]
        # 滚轮：优先让画布缩放逻辑接管。
        event.ignore()


class _PerfOverlayToolButton(QtWidgets.QToolButton):
    """面板按钮：右键/中键/滚轮放行给画布。"""

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            event.ignore()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        buttons = event.buttons()
        if buttons & Qt.MouseButton.RightButton or buttons & Qt.MouseButton.MiddleButton:
            event.ignore()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            event.ignore()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[override]
        event.ignore()


class GraphPerfOverlay(QtWidgets.QFrame):
    """GraphView 画布性能面板（仅在设置里开启时显示）。"""

    _TIMER_INTERVAL_MS: int = 200
    _DEFAULT_MAX_ROWS: int = 18

    def __init__(self, view: "GraphView", *, monitor: GraphPerfMonitor):
        # 注意：不要以 viewport() 作为父控件。
        # QGraphicsView 平移时可能走 viewport.scroll 的像素滚动优化路径，会把 viewport 子 widget 一起搬走。
        # 作为 GraphView 的直接子控件（viewport 的兄弟层）可天然规避该问题。
        super().__init__(view)
        self._view: GraphView = view
        self._monitor: GraphPerfMonitor = monitor

        self.setObjectName("graphPerfOverlay")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.setStyleSheet(
            ThemeManager.graph_search_overlay_style()
            + f"""
            QFrame#graphPerfOverlay {{
                background-color: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER_LIGHT};
                border-radius: {Sizes.RADIUS_MEDIUM}px;
            }}
            QLabel#graphPerfText {{
                color: {Colors.TEXT_PRIMARY};
            }}
            QFrame#graphPerfOverlay QToolButton {{
                border: none;
                padding: 4px 8px;
                border-radius: {Sizes.RADIUS_SMALL}px;
                color: {Colors.TEXT_PRIMARY};
                background-color: transparent;
            }}
            QFrame#graphPerfOverlay QToolButton:hover {{
                background-color: {Colors.BG_CARD_HOVER};
            }}
            QFrame#graphPerfOverlay QToolButton:pressed {{
                background-color: {Colors.BG_SELECTED_HOVER};
            }}
            """
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QtWidgets.QWidget(self)
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self._title = QtWidgets.QLabel("画布性能（拖拽/缩放/重绘）", header)
        title_font = self._title.font()
        title_font.setBold(True)
        self._title.setFont(title_font)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        header_layout.addWidget(self._title, 1)

        self._copy_button = _PerfOverlayToolButton(header)
        self._copy_button.setText("复制")
        self._copy_button.setToolTip("复制性能面板内容到剪贴板")
        self._copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_button.clicked.connect(self._copy_all_text)
        header_layout.addWidget(self._copy_button, 0, Qt.AlignmentFlag.AlignRight)

        layout.addWidget(header)

        self._label = _PerfOverlayTextLabel("", self)
        self._label.setObjectName("graphPerfText")
        self._label.setFont(ui_fonts.monospace_font(9))
        self._label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._label.setCursor(Qt.CursorShape.IBeamCursor)
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._label.setWordWrap(False)
        layout.addWidget(self._label)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(int(self._TIMER_INTERVAL_MS))
        self._timer.timeout.connect(self._refresh_text)

        self.hide()

    def start(self) -> None:
        self._timer.start()
        self._refresh_text()
        self.reposition()
        self.show()
        self.raise_()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        # 面板边距区域同样放行右键/中键平移。
        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            event.ignore()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        buttons = event.buttons()
        if buttons & Qt.MouseButton.RightButton or buttons & Qt.MouseButton.MiddleButton:
            event.ignore()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            event.ignore()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[override]
        # 滚轮：优先让画布缩放逻辑接管。
        event.ignore()

    def _copy_all_text(self) -> None:
        text = str(self._label.text() or "")
        if text.strip() == "":
            return
        cb = QtWidgets.QApplication.clipboard()
        if cb is None:
            return
        cb.setText(text)
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "已复制")

    def reposition(self) -> None:
        viewport_widget = self._view.viewport() if hasattr(self._view, "viewport") else None
        if viewport_widget is None:
            return
        viewport_geom = viewport_widget.geometry()
        if viewport_geom.isNull():
            return

        margin = 12
        show_coordinates = bool(getattr(self._view, "show_coordinates", False))
        ruler_height = 30 if show_coordinates else 0
        ruler_width = 80 if show_coordinates else 0

        x = int(viewport_geom.x() + ruler_width + margin)
        y = int(viewport_geom.y() + ruler_height + margin)

        min_width = 280
        max_width = 520
        available_width = int(viewport_geom.width() - ruler_width - margin * 2)
        if available_width <= 0:
            return
        width = int(min(max_width, max(min_width, available_width)))
        if width > available_width:
            width = int(available_width)

        # 高度按“固定行数”估算，避免频繁 sizeHint 抖动
        line_h = 15
        base_lines = 13  # 摘要/快照/空行/Top: 等固定行数（标题行由 header 占用）
        desired_lines = int(base_lines + int(self._DEFAULT_MAX_ROWS))
        # header 约 24px + margins
        height = int(desired_lines * line_h + 18 + 26)
        available_height = int(viewport_geom.height() - (y - viewport_geom.y()) - margin)
        if available_height > 0:
            height = int(min(height, max(60, available_height)))
        self.setGeometry(x, y, width, height)

    def _refresh_text(self) -> None:
        view = self._view
        scene = view.scene() if hasattr(view, "scene") else None

        scale = 1.0
        get_transform = getattr(view, "transform", None)
        if callable(get_transform):
            t = get_transform()
            if isinstance(t, QtGui.QTransform):
                scale = float(t.m11())

        panning = False
        controller = getattr(view, "interaction_controller", None)
        if controller is not None:
            panning = bool(getattr(controller, "is_panning", False))

        node_items = len(getattr(scene, "node_items", {}) or {}) if scene is not None else 0
        edge_items = len(getattr(scene, "edge_items", {}) or {}) if scene is not None else 0
        batched_layer = bool(getattr(scene, "_batched_fast_preview_edge_layer", None)) if scene is not None else False
        fast_preview = bool(getattr(scene, "fast_preview_mode", False)) if scene is not None else False

        fps = self._monitor.get_fps()

        # 优先展示我们关心的段；其余段（若存在）会按 avg 排序补齐到 top 列表。
        preferred = [
            "view.paint.total",
            "view.paint.scene",
            "scene.drawBackground.total",
            "scene.drawForeground.total",
            "view.drawItems.total",
            "scene.drawItems.total",
            "items.paint.edge.total",
            "items.paint.node.total",
            "items.paint.port.total",
            "items.paint.port_settings.total",
            "items.paint.batched_edges.total",
            "items.paint.fast_edge.total",
            "items.paint.fast_node.total",
            "view.paint.ruler",
            "view.paint.minimap_position",
            "view.paint.top_right_controls",
            "controller.scrollContentsBy.total",
        ]
        stats = self._monitor.get_series_stats(preferred)
        preferred_names = {s.name for s in stats}
        extra = [
            s
            for s in sorted(self._monitor.get_all_series_stats(), key=lambda x: x.avg_ms, reverse=True)
            if s.name not in preferred_names
        ]
        top_list = (stats + extra)[: int(self._DEFAULT_MAX_ROWS)]

        # 最大开销：跳过 total 行，避免“永远是 total”。
        biggest: PerfSeriesStats | None = None
        for s in sorted(top_list, key=lambda x: x.avg_ms, reverse=True):
            if s.name.endswith(".total") and s.name in ("view.paint.total",):
                continue
            biggest = s
            break

        lines: List[str] = []
        lines.append(
            f"scale={scale:.2f} ({int(round(scale * 100.0))}%)  panning={int(panning)}  fast_preview={int(fast_preview)}"
        )
        lines.append(
            f"items: nodes={node_items}  edges={edge_items}  batched_edges={int(batched_layer)}  fps≈{fps:.1f}"
        )
        if biggest is not None:
            lines.append(f"最大开销：{biggest.name} avg={biggest.avg_ms:.2f}ms max={biggest.max_ms:.2f}ms")
        else:
            lines.append("最大开销：-")

        # last-frame counts（来自 per-frame inc/flush）
        last_counts = self._monitor.get_last_counts()
        view_draw_items_calls = int(last_counts.get("view.drawItems.calls", 0) or 0)
        view_draw_items_items = int(last_counts.get("view.drawItems.items", 0) or 0)
        scene_draw_items_calls = int(last_counts.get("scene.drawItems.calls", 0) or 0)
        scene_draw_items_items = int(last_counts.get("scene.drawItems.items", 0) or 0)
        edge_paint_calls = int(last_counts.get("items.paint.edge.calls", 0) or 0)
        node_paint_calls = int(last_counts.get("items.paint.node.calls", 0) or 0)
        port_paint_calls = int(last_counts.get("items.paint.port.calls", 0) or 0)
        gear_paint_calls = int(last_counts.get("items.paint.port_settings.calls", 0) or 0)
        batched_layer_calls = int(last_counts.get("items.paint.batched_edges.calls", 0) or 0)
        batched_edges_drawn = int(last_counts.get("items.paint.batched_edges.edges_drawn", 0) or 0)

        if view_draw_items_calls or view_draw_items_items or scene_draw_items_calls or scene_draw_items_items:
            parts: List[str] = []
            if view_draw_items_calls or view_draw_items_items:
                parts.append(f"view calls={view_draw_items_calls}  items={view_draw_items_items}")
            if scene_draw_items_calls or scene_draw_items_items:
                parts.append(f"scene calls={scene_draw_items_calls}  items={scene_draw_items_items}")
            lines.append("drawItems(last): " + "  |  ".join(parts))
        if edge_paint_calls or node_paint_calls or port_paint_calls or gear_paint_calls or batched_layer_calls:
            lines.append(
                "paint calls(last): "
                + f"edge={edge_paint_calls}  node={node_paint_calls}  port={port_paint_calls}  gear={gear_paint_calls}"
                + (
                    f"  batched_layer={batched_layer_calls}  batched_edges={batched_edges_drawn}"
                    if batched_layer_calls
                    else ""
                )
            )

        slowest_last = self._monitor.get_last_slowest_items()
        if slowest_last:
            top_slowest = slowest_last[:5]
            slowest_text = ", ".join([f"{dt_ms:.2f}ms {lab}" for dt_ms, lab in top_slowest])
            lines.append(f"slowest(last): {slowest_text}")

        # 未归因开销（Qt draw pipeline / item 枚举等）：用“上一帧快照”算差值，避免靠 rolling avg 误差太大
        frame_ms_by_name = self._monitor.get_last_frame_ms_by_name()
        scene_last_ms = float(frame_ms_by_name.get("view.paint.scene", 0.0) or 0.0)
        accounted_last_ms = 0.0
        for k in (
            "scene.drawBackground.total",
            "scene.drawForeground.total",
            "items.paint.node.total",
            "items.paint.edge.total",
            "items.paint.port.total",
            "items.paint.port_settings.total",
            "items.paint.batched_edges.total",
            "items.paint.fast_edge.total",
            "items.paint.fast_node.total",
        ):
            accounted_last_ms += float(frame_ms_by_name.get(str(k), 0.0) or 0.0)
        unaccounted_last_ms = float(scene_last_ms - accounted_last_ms)
        if scene_last_ms > 0.0:
            lines.append(
                f"未归因(last)=scene-已统计: {unaccounted_last_ms:.2f}ms  (scene={scene_last_ms:.2f}  已统计={accounted_last_ms:.2f})"
            )
            view_draw_last_ms = float(frame_ms_by_name.get("view.drawItems.total", 0.0) or 0.0)
            if view_draw_last_ms > 0.0:
                item_paints_ms = 0.0
                for k in (
                    "items.paint.node.total",
                    "items.paint.edge.total",
                    "items.paint.port.total",
                    "items.paint.port_settings.total",
                    "items.paint.batched_edges.total",
                    "items.paint.fast_edge.total",
                    "items.paint.fast_node.total",
                ):
                    item_paints_ms += float(frame_ms_by_name.get(str(k), 0.0) or 0.0)
                draw_unaccounted_ms = float(view_draw_last_ms - item_paints_ms)
                lines.append(
                    f"drawItems未归因(last)=drawItems-绘制: {draw_unaccounted_ms:.2f}ms  (drawItems={view_draw_last_ms:.2f}  绘制={item_paints_ms:.2f})"
                )

        # panning 快照：记录“最后一次拖拽帧”的分解，方便松手后复制
        pan_ms = self._monitor.get_last_panning_frame_ms_by_name()
        if pan_ms:
            pan_scene_ms = float(pan_ms.get("view.paint.scene", 0.0) or 0.0)
            pan_accounted_ms = 0.0
            for k in (
                "scene.drawBackground.total",
                "scene.drawForeground.total",
                "items.paint.node.total",
                "items.paint.edge.total",
                "items.paint.port.total",
                "items.paint.port_settings.total",
                "items.paint.batched_edges.total",
                "items.paint.fast_edge.total",
                "items.paint.fast_node.total",
            ):
                pan_accounted_ms += float(pan_ms.get(str(k), 0.0) or 0.0)
            pan_unaccounted_ms = float(pan_scene_ms - pan_accounted_ms)
            pan_biggest_name = "-"
            pan_biggest_ms = 0.0
            for k, v in sorted(pan_ms.items(), key=lambda kv: float(kv[1] or 0.0), reverse=True):
                key = str(k or "").strip()
                if key in ("view.paint.total",):
                    continue
                pan_biggest_name = key
                pan_biggest_ms = float(v or 0.0)
                break
            lines.append(
                f"panning(last): 最大={pan_biggest_name} {pan_biggest_ms:.2f}ms  scene={pan_scene_ms:.2f}ms  未归因={pan_unaccounted_ms:.2f}ms"
            )
            pan_counts = self._monitor.get_last_panning_counts()
            pan_edge = int(pan_counts.get("items.paint.edge.calls", 0) or 0)
            pan_node = int(pan_counts.get("items.paint.node.calls", 0) or 0)
            pan_port = int(pan_counts.get("items.paint.port.calls", 0) or 0)
            pan_gear = int(pan_counts.get("items.paint.port_settings.calls", 0) or 0)
            if pan_edge or pan_node or pan_port or pan_gear:
                lines.append(f"panning paint calls: edge={pan_edge}  node={pan_node}  port={pan_port}  gear={pan_gear}")
            pan_slowest = self._monitor.get_last_panning_slowest_items()
            if pan_slowest:
                top3 = pan_slowest[:3]
                lines.append("panning slowest: " + ", ".join([f"{dt_ms:.2f}ms {lab}" for dt_ms, lab in top3]))
        lines.append("")
        lines.append("Top:")
        for s in top_list:
            lines.append(f"- {s.name:<30} avg={s.avg_ms:>6.2f}  max={s.max_ms:>6.2f}  last={s.last_ms:>6.2f}")

        self._label.setText("\n".join(lines))

